import type { Metadata } from "next";
import { Metrics } from "@/components/Bits";
import { site } from "@/lib/data";
import { STREAMLIT } from "@/lib/format";

export const metadata: Metadata = { title: "How it works" };

export default function AboutPage() {
  const info = site();
  const when = info.updatedAt
    ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(info.updatedAt))
    : null;
  return (
    <>
      <h1>
        How it <em>works</em>
      </h1>
      <p className="lede">
        FootyMinds turns free football data into answers for Europe&apos;s top five leagues.
        {when ? ` The numbers were last refreshed on ${when}.` : ""} This Vercel site reads the same precomputed tables as the Streamlit app. Voting still happens there.
      </p>
      <Metrics
        items={[
          { label: "Results called, all five leagues", value: info.about.allModel ?? "–" },
          { label: "Bookmakers, same games", value: info.about.allBook ?? "–" },
          { label: "Always picking home", value: info.about.alwaysHome ?? "–" },
        ]}
      />
      <h2>Where the numbers come from</h2>
      <table>
        <tbody>
          <tr>
            <td>Expected goals, shots, chances, fixtures</td>
            <td>Understat</td>
          </tr>
          <tr>
            <td>Results since 2016 and bookmaker odds</td>
            <td>football-data.co.uk</td>
          </tr>
          <tr>
            <td>Market values{info.about.snapshot ? ` (as of ${info.about.snapshot})` : ""}</td>
            <td>Transfermarkt, via transfermarkt-datasets</td>
          </tr>
          <tr>
            <td>Premier League tackles, interceptions, saves</td>
            <td>Fantasy Premier League API</td>
          </tr>
          <tr>
            <td>Fan VAR calls, referees, line-ups</td>
            <td>ESPN match commentary</td>
          </tr>
          <tr>
            <td>Highlights</td>
            <td>Official league channels on YouTube</td>
          </tr>
        </tbody>
      </table>
      <h2>Coverage on the 2025/26 test</h2>
      <table>
        <thead>
          <tr>
            <th>League</th>
            <th>Results, us / bookies</th>
            <th>Over 2.5, us / bookies</th>
            <th>Exact score in top 3</th>
            <th>Value error</th>
            <th>Defence</th>
          </tr>
        </thead>
        <tbody>
          {info.about.rows.map((row) => (
            <tr key={row.league}>
              <td>{row.league}</td>
              <td>{row.results}</td>
              <td>{row.over}</td>
              <td>{row.score}</td>
              <td>{row.value}</td>
              <td>{row.defence}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted">Tested on the whole 2025/26 season, using only games before each one. A typical value error is the median gap versus Transfermarkt.</p>
      <h2>Fan VAR and the offside check</h2>
      <p>
        Penalties, red cards, VAR checks and goals ruled out are pulled from commentary after each round. Yellow cards are listed under every match. Votes, flags and the referee report card live on{" "}
        <a href={STREAMLIT}>the Streamlit app</a>, one vote per device, no account. The offside line tool, where you click the picture yourself, is there too. It uses YOLOX to spot players and is not rebuilt on this site.
      </p>
      <p>These are probabilities, not certainties. The models do not know about a late injury beyond what is already in the data.</p>
    </>
  );
}
