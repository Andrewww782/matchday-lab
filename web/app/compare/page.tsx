import type { Metadata } from "next";
import Link from "next/link";
import { scout, site } from "@/lib/data";

export const metadata: Metadata = { title: "Head-to-head" };

const STATS = ["goals", "npxG", "shots", "xA", "key_passes", "xGChain"];

export default async function ComparePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const all = scout();
  const labels = site().scoutMeta.labels;
  const wanted = ["a", "b", "c"].map((key) => (typeof sp[key] === "string" ? sp[key] : "")).filter(Boolean);
  const chosen = all.filter((row) => wanted.includes(playerLabel(row)));

  return (
    <>
      <h1>
        Head-to-<em>head</em>
      </h1>
      <p className="lede">
        Percentiles against other players in the same position across the top five leagues. 100 means he does that more than everyone else in the group.{" "}
        <Link href="/find">Find a player</Link>, then add him here.
      </p>
      <form className="filters" action="/compare">
        {(["a", "b", "c"] as const).map((key, index) => (
          <label key={key}>
            Player {index + 1}
            <select name={key} defaultValue={typeof sp[key] === "string" ? sp[key] : ""}>
              <option value="">None</option>
              {all.map((row) => {
                const label = `${row.name} · ${row.team}`;
                return (
                  <option key={row.pid} value={label}>
                    {label}
                  </option>
                );
              })}
            </select>
          </label>
        ))}
        <button type="submit">Compare</button>
      </form>
      {chosen.length < 2 ? (
        <p className="note">Pick at least two players. The labels are Name · Club, the same ones used on the player page.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Stat</th>
              {chosen.map((row) => (
                <th key={row.pid} className="num">
                  {row.web || row.name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {STATS.map((stat) => (
              <tr key={stat}>
                <td>{labels[stat] ?? stat}</td>
                {chosen.map((row) => {
                  const value = row.pctEu[stat] ?? row.pct[stat];
                  return (
                    <td key={row.pid} className="num">
                      {value == null ? "–" : `${value.toFixed(0)}%`}
                      {value != null ? (
                        <div className="pct" aria-hidden>
                          <span style={{ width: `${value}%` }} />
                        </div>
                      ) : null}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="muted">Defensive numbers exist for the Premier League only, so this table stays with attacking and creative play.</p>
    </>
  );
}

function playerLabel(row: { name: string; team: string }) {
  return `${row.name} · ${row.team}`;
}
