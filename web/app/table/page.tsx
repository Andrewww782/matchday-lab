import type { Metadata } from "next";
import { LeagueBar } from "@/components/Bits";
import { resolveLeague, site, tables } from "@/lib/data";
import { pct, streamlit } from "@/lib/format";

export const metadata: Metadata = { title: "Where will they finish?" };

export default async function TablePage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const league = resolveLeague(sp);
  const info = site().leagues[league];
  const table = tables()[league];
  const playoff = info.playoff != null;

  return (
    <>
      <h1>
        Where will they <em>finish?</em>
      </h1>
      <p className="lede">
        {table?.simulated
          ? "The rest of the season is played 10,000 times from today's match chances, with each club's strength nudged a little so the table is not falsely certain."
          : "Current table from games already played. Season odds will appear after the next data export."}
      </p>
      <LeagueBar league={league} path="/table" />
      <p className="muted">
        Champions League = top {info.cl}. Relegated = bottom {info.relegated}.
        {playoff ? ` Play-off = ${info.playoff}th.` : ""} What-if results stay on the{" "}
        <a href={streamlit("/table", { league })}>Streamlit season page</a>.
      </p>
      <table>
        <thead>
          <tr>
            <th>Club</th>
            <th className="num">Pts</th>
            <th className="num">P</th>
            <th className="num">GD</th>
            {table?.simulated ? (
              <>
                <th className="num">Exp pts</th>
                <th className="num">Title</th>
                <th className="num">Champions League</th>
                {playoff ? <th className="num">Play-off</th> : null}
                <th className="num">Relegated</th>
              </>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {table?.rows.map((row) => (
            <tr key={row.team}>
              <td>{row.team}</td>
              <td className="num">{row.pts}</td>
              <td className="num">{row.p}</td>
              <td className="num">{row.gd}</td>
              {table.simulated ? (
                <>
                  <td className="num">{row.expPts?.toFixed(0)}</td>
                  <td className="num">{pct(row.title)}</td>
                  <td className="num">{pct(row.cl)}</td>
                  {playoff ? <td className="num">{pct(row.playoff)}</td> : null}
                  <td className="num">{pct(row.relegated)}</td>
                </>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
