import type { Metadata } from "next";
import Link from "next/link";
import { LeagueBar, WhyBars } from "@/components/Bits";
import { playerByLabel, players, resolveLeague, site, values } from "@/lib/data";
import { href, money } from "@/lib/format";

export const metadata: Metadata = { title: "What's he worth?" };

export default async function ValuePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const league = resolveLeague(sp);
  const info = site().leagues[league];
  const picked = playerByLabel(typeof sp.player === "string" ? sp.player : undefined);
  const value = picked ? values().find((row) => row.pid === picked.pid) : undefined;
  const names = new Map(players().map((p) => [p.pid, p]));
  const list = values()
    .filter((row) => row.league === league && row.ratio != null)
    .sort((a, b) => (b.ratio ?? 0) - (a.ratio ?? 0))
    .slice(0, 12);

  return (
    <>
      <h1>
        What&apos;s he <em>worth?</em>
      </h1>
      <p className="lede">
        A blend of models guesses a fee from what he does on the pitch. It never sees his old price. Market values are the {site().about.snapshot ?? "June 2026"} Transfermarkt snapshot.
      </p>
      <LeagueBar league={league} path="/value" keep={{ player: picked?.label }} />
      {picked && value ? (
        <article className="card">
          <h2 style={{ textTransform: "none", fontFamily: "DM Sans, sans-serif" }}>{picked.name}</h2>
          <p className="muted">
            {picked.team} · {picked.leagueName} · {value.verdict}
          </p>
          <p>
            Numbers say <b>{money(value.est)}</b> · Market <b>{money(value.market)}</b>
          </p>
          <WhyBars items={value.factors} home="higher value" away="lower value" />
        </article>
      ) : (
        <p className="note">
          Open a player from the list, or <Link href="/find">search for one</Link>.
        </p>
      )}
      <section>
        <div className="eyebrow">{info.name}</div>
        <h2>Biggest gaps</h2>
        <table>
          <thead>
            <tr>
              <th>Player</th>
              <th>Verdict</th>
              <th className="num">Numbers say</th>
              <th className="num">Market</th>
            </tr>
          </thead>
          <tbody>
            {list.map((row) => {
              const player = names.get(row.pid);
              if (!player) return null;
              return (
                <tr key={row.pid}>
                  <td>
                    <Link href={href("/value", { league, player: player.label })}>{player.name}</Link>
                  </td>
                  <td>{row.verdict}</td>
                  <td className="num">{money(row.est)}</td>
                  <td className="num">{money(row.market)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    </>
  );
}
