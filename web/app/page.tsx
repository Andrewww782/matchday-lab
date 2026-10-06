import Link from "next/link";
import { FixtureCard, LeagueBar } from "@/components/Bits";
import { incidents, players, resolveLeague, site, upcoming, values } from "@/lib/data";
import { drama, href, money, pct } from "@/lib/format";

export default async function Home({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const league = resolveLeague(sp);
  const info = site().leagues[league];
  const theName = league === "EPL" ? `the ${info.name}` : info.name;
  const week = upcoming()
    .filter((row) => row.league === league && row.kickoff)
    .sort((a, b) => (a.kickoff! < b.kickoff! ? -1 : 1));
  const gw = week[0]?.gw;
  const games = gw == null ? [] : week.filter((row) => row.gw === gw);

  const calls = incidents().filter((row) => row.league === league && row.big);
  const lastGw = calls.reduce((max, row) => (row.gw != null && row.gw > max ? row.gw : max), 0);
  const hot = calls
    .filter((row) => row.gw === lastGw)
    .sort((a, b) => drama(b.kind) - drama(a.kind) || (b.kickoff ?? "").localeCompare(a.kickoff ?? ""))
    .slice(0, 3);

  const names = new Map(players().map((p) => [p.pid, p]));
  const bargains = values()
    .filter((row) => row.league === league && (row.market ?? 0) >= 3e6 && row.ratio != null)
    .sort((a, b) => (b.ratio ?? 0) - (a.ratio ?? 0))
    .slice(0, 8)
    .map((row) => ({ ...row, player: names.get(row.pid) }))
    .filter((row) => row.player);

  return (
    <>
      <p className="hero-tag">
        <span className="sticker">You&apos;re the VAR</span>
      </p>
      <h1>
        This <em>week</em>
      </h1>
      <p className="lede">
        Every big refereeing call in {theName}, plus who is favourite and who looks underpriced.
        {lastGw ? ` ${info.round} ${lastGw} has the latest calls.` : ""}
      </p>
      <LeagueBar league={league} path="/" />

      {hot.length ? (
        <section>
          <div className="eyebrow">Your call</div>
          <h2>Hottest calls right now</h2>
          <div className="grid-3">
            {hot.map((call) => (
              <article className="card" key={call.id}>
                <span className="sticker red">{call.kind.replaceAll("_", " ")}</span>
                <h3>{call.headline}</h3>
                <p className="muted">
                  {call.home} {call.score} {call.away}
                  {call.minute != null ? ` · ${call.minute}'` : ""}
                </p>
                <Link className="btn" href={href("/var", { league, gw: call.gw ?? undefined })}>
                  Open the call
                </Link>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section>
        <div className="eyebrow">This week&apos;s games</div>
        <h2>
          {gw != null ? `${info.round} ${gw} predictions` : "Predictions"}
        </h2>
        {games.length ? (
          <div className="grid-2">
            {games.map((row) => (
              <FixtureCard key={`${row.home}-${row.away}`} row={row} />
            ))}
          </div>
        ) : (
          <p className="note">No upcoming {info.name} fixtures right now. The season may be on a break.</p>
        )}
      </section>

      <section className="split">
        <div>
          <div className="eyebrow">Transfer watch</div>
          <h2>Bargains in {info.name}</h2>
          <p className="muted">Players whose numbers say they are worth more than their market value. Values are from {site().about.snapshot ?? "the latest snapshot"}.</p>
          <table>
            <thead>
              <tr>
                <th>Player</th>
                <th>Club</th>
                <th className="num">Numbers say</th>
                <th className="num">Market</th>
              </tr>
            </thead>
            <tbody>
              {bargains.map((row) => (
                <tr key={row.pid}>
                  <td>
                    <Link href={href("/value", { league, player: row.player!.label })}>{row.player!.name}</Link>
                  </td>
                  <td>{row.player!.team}</td>
                  <td className="num">{money(row.est)}</td>
                  <td className="num">{money(row.market)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <aside>
          <h2>Explore</h2>
          <div className="links">
            <Link href={href("/var", { league })}>
              <strong>Fan VAR</strong>
              Judge every big refereeing call.
            </Link>
            <Link href={href("/match", { league })}>
              <strong>Who wins?</strong>
              Pick any two clubs and see why.
            </Link>
            <Link href={href("/table", { league })}>
              <strong>Season odds</strong>
              Title, Champions League and relegation.
            </Link>
            <Link href="/find">
              <strong>Find a player</strong>
              Value, style and similar players.
            </Link>
          </div>
          <p className="muted">A 60% favourite still loses 4 times in 10. {pct(0.6)} is not a promise.</p>
        </aside>
      </section>
    </>
  );
}
