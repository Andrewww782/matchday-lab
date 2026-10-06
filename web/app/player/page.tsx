import type { Metadata } from "next";
import Link from "next/link";
import { ClubName, Metrics } from "@/components/Bits";
import { playerByLabel, players, scout, values } from "@/lib/data";
import { href, money } from "@/lib/format";

export const metadata: Metadata = { title: "Player profile" };

export default async function PlayerPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const label = typeof sp.player === "string" ? sp.player : undefined;
  const player = playerByLabel(label);
  const names = players();

  return (
    <>
      <h1>
        Player <em>profile</em>
      </h1>
      <p className="lede">Form, value and style for any player in Europe&apos;s top five leagues.</p>
      <form className="filters" action="/player">
        <label>
          Player
          <select name="player" defaultValue={player?.label ?? ""}>
            <option value="">Choose a player</option>
            {names.map((row) => (
              <option key={row.pid} value={row.label}>
                {row.label}
              </option>
            ))}
          </select>
        </label>
        <Link className="btn ink" href="/find">
          Search instead
        </Link>
        <button type="submit">Show</button>
      </form>
      {!player ? (
        <p className="note">Pick a player, or use Find a player to search by name.</p>
      ) : (
        <Profile label={player.label} />
      )}
    </>
  );
}

function Profile({ label }: { label: string }) {
  const player = playerByLabel(label)!;
  const value = values().find((row) => row.pid === player.pid);
  const style = scout().find((row) => row.pid === player.pid);
  const where = player.league === "EPL" ? "Premier League" : "top-5-league";
  const pcts = style ? (player.league === "EPL" ? style.pct : style.pctEu) : {};
  const strengths = Object.entries(pcts)
    .filter((entry): entry is [string, number] => entry[1] != null)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2);

  return (
    <>
      <article className="card">
        <h2 style={{ textTransform: "none", fontFamily: "DM Sans, sans-serif" }}>{player.name}</h2>
        <p>
          <ClubName name={player.team} /> · {player.leagueName} · {player.sub || player.pos}
          {player.age != null ? ` · age ${player.age}` : ""}
        </p>
      </article>
      <Metrics
        items={[
          { label: "Minutes", value: player.minutes?.toFixed(0) ?? "–" },
          { label: "Non-penalty goals", value: player.npg?.toFixed(1) ?? "–" },
          { label: "Expected assists", value: player.xa?.toFixed(1) ?? "–" },
          { label: "Market value", value: money(player.value) },
        ]}
      />
      {value ? (
        <section>
          <div className="eyebrow">Value</div>
          <h2>{value.verdict}</h2>
          <p>
            Numbers say <b>{money(value.est)}</b>. Market <b>{money(value.market)}</b>.
          </p>
          <Link className="btn" href={href("/value", { league: player.league, player: player.label })}>
            Full value breakdown
          </Link>
        </section>
      ) : null}
      {style ? (
        <section>
          <div className="eyebrow">Style</div>
          <h2>{style.style}</h2>
          {strengths.length ? (
            <p>
              Stands out for{" "}
              {strengths.map(([key, score], index) => (
                <span key={key}>
                  {index ? " and " : ""}
                  <b>{key.replaceAll("_", " ")}</b> (better than {score.toFixed(0)}% of {where} {player.pos}s)
                </span>
              ))}
              .
            </p>
          ) : null}
          <Link className="btn" href={href("/scout", { player: player.label })}>
            Similar players
          </Link>
        </section>
      ) : null}
      <p>
        <Link href={href("/compare", { a: player.label })}>Compare him</Link>
        {" · "}
        <Link href={href("/team", { league: player.league, team: player.team })}>{player.team}</Link>
      </p>
    </>
  );
}
