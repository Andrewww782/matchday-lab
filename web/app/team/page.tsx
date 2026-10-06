import type { Metadata } from "next";
import Link from "next/link";
import { ClubName, FixtureCard, FormPills, LeagueBar, Metrics } from "@/components/Bits";
import { formOf, incidents, players, resolveLeague, site, teamState, teamsIn, upcoming } from "@/lib/data";
import { href, KIND_LABEL, money } from "@/lib/format";

export const metadata: Metadata = { title: "Club profile" };

export default async function TeamPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const league = resolveLeague(sp);
  const info = site().leagues[league];
  const clubs = teamsIn(league).map((row) => row.team);
  const nextHome = upcoming()
    .filter((row) => row.league === league && row.kickoff)
    .sort((a, b) => (a.kickoff! < b.kickoff! ? -1 : 1))[0]?.home;
  const team = typeof sp.team === "string" && clubs.includes(sp.team) ? sp.team : nextHome ?? clubs[0];
  const form = formOf(league, team);
  const state = teamState().find((row) => row.league === league && row.team === team);
  const next = upcoming()
    .filter((row) => row.league === league && row.kickoff && (row.home === team || row.away === team))
    .sort((a, b) => (a.kickoff! < b.kickoff! ? -1 : 1))
    .slice(0, 5);
  const squad = players()
    .filter((row) => row.team === team)
    .sort((a, b) => (b.npg ?? 0) + (b.xa ?? 0) - ((a.npg ?? 0) + (a.xa ?? 0)))
    .slice(0, 5);
  const calls = incidents()
    .filter((row) => row.big && (row.home === team || row.away === team))
    .sort((a, b) => (b.kickoff ?? "").localeCompare(a.kickoff ?? ""))
    .slice(0, 3);

  return (
    <>
      <h1>
        Club <em>profile</em>
      </h1>
      <p className="lede">Recent form, what is next, who to watch, and the big calls in their games.</p>
      <LeagueBar league={league} path="/team" keep={{ team }} />
      <form className="filters" action="/team">
        <input type="hidden" name="league" value={league} />
        <label>
          Club
          <select name="team" defaultValue={team}>
            {clubs.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
        <button type="submit">Show</button>
      </form>

      <article className="card">
        <ClubName name={team} />
        <p className="muted">{info.name}</p>
      </article>

      <section>
        <div className="eyebrow">Form</div>
        <h2>How have they been playing?</h2>
        <FormPills results={form} />
        {state ? (
          <Metrics
            items={[
              { label: "Elo", value: state.elo?.toFixed(0) ?? "–" },
              { label: "Points per game, last 5", value: state.pts5?.toFixed(2) ?? "–" },
              { label: "xG for, last 5", value: state.xgf5?.toFixed(2) ?? "–" },
              { label: "xG against, last 5", value: state.xga5?.toFixed(2) ?? "–" },
            ]}
          />
        ) : (
          <p className="muted">No rolling form numbers yet for this club.</p>
        )}
      </section>

      <section>
        <div className="eyebrow">Fixtures</div>
        <h2>What&apos;s next?</h2>
        {next.length ? (
          <div className="grid-2">
            {next.map((row) => (
              <FixtureCard key={`${row.home}-${row.away}-${row.kickoff}`} row={row} />
            ))}
          </div>
        ) : (
          <p className="note">No upcoming fixtures. The season may be finished or on a break.</p>
        )}
      </section>

      <section>
        <div className="eyebrow">Squad</div>
        <h2>Who to watch</h2>
        <p className="muted">Sorted by non-penalty goals plus expected assists, across last season and this one.</p>
        <div className="links">
          {squad.map((player) => (
            <Link key={player.pid} href={href("/player", { player: player.label })}>
              <strong>{player.name}</strong>
              {player.sub || player.pos}
              {player.age != null ? ` · age ${player.age}` : ""} · {money(player.value)} · {player.npg ?? 0} npg · {player.xa ?? 0} xA
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="eyebrow">Fan VAR</div>
        <h2>Did the refs get it right?</h2>
        {calls.length ? (
          <div className="grid-3">
            {calls.map((call) => (
              <article className="card" key={call.id}>
                <span className="sticker">{KIND_LABEL[call.kind] ?? "Call"}</span>
                <h3>{call.headline}</h3>
                <p className="muted">
                  {call.home} {call.score} {call.away}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p className="note">No big calls involving {team} yet this season.</p>
        )}
        <p>
          <Link className="btn" href={href("/var", { league })}>
            See every call
          </Link>
        </p>
      </section>
    </>
  );
}
