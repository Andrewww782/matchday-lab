import type { Metadata } from "next";
import { LeagueBar, Metrics, ProbBar, WhyBars } from "@/components/Bits";
import { pairs, resolveLeague, site, teamsIn, upcoming } from "@/lib/data";
import { href, pct, whenUK } from "@/lib/format";

export const metadata: Metadata = { title: "Who wins?" };

function favourite(home: string, away: string, ph: number, pd: number, pa: number) {
  const pick = ph >= pd && ph >= pa ? "H" : pa >= pd ? "A" : "D";
  const best = Math.max(ph, pd, pa);
  const line = pick === "H" ? `${home} win` : pick === "A" ? `${away} win` : "a draw";
  const tone = best < 0.4 ? "Too close to call" : best < 0.5 ? "Slight favourite" : best < 0.65 ? "Favourite" : "Strong favourite";
  return { line, best, tone };
}

export default async function MatchPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const league = resolveLeague(sp);
  const info = site().leagues[league];
  const clubs = teamsIn(league).map((row) => row.team);
  const nextUp = upcoming()
    .filter((row) => row.league === league && row.kickoff)
    .sort((a, b) => (a.kickoff! < b.kickoff! ? -1 : 1))[0];
  const home = typeof sp.home === "string" && clubs.includes(sp.home) ? sp.home : nextUp?.home ?? clubs[0];
  const away = typeof sp.away === "string" && clubs.includes(sp.away) ? sp.away : nextUp?.away ?? clubs[1];
  const scheduled = upcoming().find((row) => row.league === league && row.home === home && row.away === away);
  const model = scheduled ?? pairs().find((row) => row.league === league && row.home === home && row.away === away);

  return (
    <>
      <h1>
        Who <em>wins?</em>
      </h1>
      <p className="lede">Pick two clubs. The chances blend a form model with a goals model, trained only on games already played.</p>
      <LeagueBar league={league} path="/match" keep={{ home, away }} />
      <form className="filters" action="/match">
        <input type="hidden" name="league" value={league} />
        <label>
          Home
          <select name="home" defaultValue={home}>
            {clubs.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <label>
          Away
          <select name="away" defaultValue={away}>
            {clubs.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <button type="submit">Show</button>
      </form>

      {home === away ? (
        <p className="note">Pick two different clubs.</p>
      ) : !model ? (
        <p className="note">No prediction for {home} against {away} yet.</p>
      ) : (
        <>
          <p className="muted">
            {scheduled?.kickoff
              ? `${info.round} ${scheduled.gw} · ${whenUK(scheduled.kickoff, "long")}`
              : "Not a scheduled fixture, so this assumes a normal week's rest for both teams."}
          </p>
          <article className="card">
            <ProbBar home={home} away={away} ph={model.ph} pd={model.pd} pa={model.pa} />
            <p>
              <b>
                Most likely: {favourite(home, away, model.ph, model.pd, model.pa).line} ({pct(favourite(home, away, model.ph, model.pd, model.pa).best)})
              </b>{" "}
              · {favourite(home, away, model.ph, model.pd, model.pa).tone}
            </p>
          </article>
          {model.scores.length ? (
            <section>
              <div className="eyebrow">Scorelines</div>
              <h2>The score</h2>
              <p>
                Expected goals: <b>{home} {model.xgH?.toFixed(1)} – {model.xgA?.toFixed(1)} {away}</b>. The single most likely score usually happens only about 1 time in 8.
              </p>
              <div className="scores">
                {model.scores.slice(0, 5).map((score) => (
                  <span className="chip" key={score.score}>
                    <b>{score.score}</b>
                    {pct(score.p)}
                  </span>
                ))}
              </div>
              <Metrics
                items={[
                  { label: "Both teams score", value: pct(model.btts) },
                  { label: "Over 2.5 goals", value: pct(model.over) },
                  { label: `${home} clean sheet`, value: pct(model.csH) },
                  { label: `${away} clean sheet`, value: pct(model.csA) },
                ]}
              />
            </section>
          ) : null}
          <section>
            <div className="eyebrow">The reasons</div>
            <h2>Why?</h2>
            <WhyBars items={model.factors} home={home} away={away} />
            <p>
              <a href={href("/team", { league, team: home })}>{home} profile</a>
              {" · "}
              <a href={href("/team", { league, team: away })}>{away} profile</a>
            </p>
          </section>
        </>
      )}
    </>
  );
}
