import Link from "next/link";
import { club, site, type Factor, type MatchOdds } from "@/lib/data";
import { href, pct, textOn, whenUK } from "@/lib/format";

export function LeagueBar({
  league,
  path,
  keep,
}: {
  league: string;
  path: string;
  keep?: Record<string, string | undefined>;
}) {
  const info = site();
  return (
    <nav className="leagues" aria-label="League">
      {info.order.map((key) => (
        <Link key={key} href={href(path, { ...keep, league: key })} className={key === league ? "on" : undefined}>
          {info.leagues[key].name}
        </Link>
      ))}
    </nav>
  );
}

export function ClubName({ name }: { name: string }) {
  const row = club(name);
  const colour = row?.colour ?? "#161616";
  return (
    <span className="club">
      <i className="dot" style={{ background: colour }} aria-hidden />
      {row?.short ? (
        <span className="short" style={{ background: colour, color: textOn(colour) }}>
          {row.short}
        </span>
      ) : null}
      {name}
    </span>
  );
}

export function ProbBar({ home, away, ph, pd, pa }: { home: string; away: string; ph: number; pd: number; pa: number }) {
  return (
    <div>
      <div className="bar" role="img" aria-label={`${home} ${pct(ph)}, draw ${pct(pd)}, ${away} ${pct(pa)}`}>
        <i className="home" style={{ width: pct(ph) }} />
        <i className="draw" style={{ width: pct(pd) }} />
        <i className="away" style={{ width: pct(pa) }} />
      </div>
      <div className="legend">
        <span>{home} {pct(ph)}</span>
        <span className="draw">Draw {pct(pd)}</span>
        <span>{away} {pct(pa)}</span>
      </div>
    </div>
  );
}

export function FixtureCard({ row }: { row: MatchOdds }) {
  const soon = row.kickoff ? Date.now() <= new Date(row.kickoff).getTime() && new Date(row.kickoff).getTime() <= Date.now() + 48 * 3600 * 1000 : false;
  const best = row.scores[0];
  return (
    <article className="card">
      <p className="muted">
        {soon ? "Soon · " : ""}
        {whenUK(row.kickoff)}
      </p>
      <div className="row">
        <ClubName name={row.home} />
        <span className="muted">vs</span>
        <ClubName name={row.away} />
      </div>
      <ProbBar home={row.home} away={row.away} ph={row.ph} pd={row.pd} pa={row.pa} />
      {best ? (
        <p className="muted">
          Likely score <b>{best.score}</b>
          {row.over != null ? ` · Over 2.5 goals ${pct(row.over)}` : ""}
        </p>
      ) : null}
      <Link className="btn" href={href("/match", { league: row.league, home: row.home, away: row.away })}>
        Why?
      </Link>
    </article>
  );
}

export function WhyBars({ items, home, away }: { items: Factor[]; home: string; away: string }) {
  const shown = [...items].filter((item) => Math.abs(item.v) >= 0.5).sort((a, b) => Math.abs(b.v) - Math.abs(a.v));
  if (!shown.length) return <p>These two sides look evenly matched on every measure.</p>;
  const max = Math.max(...shown.map((item) => Math.abs(item.v)), 1);
  return (
    <div className="why">
      <div className="why-key">
        <span>Helps {away}</span>
        <span>Helps {home}</span>
      </div>
      {shown.map((item) => (
        <div className="why-row" key={item.label}>
          <span>{item.label}</span>
          <div className="track" aria-hidden>
            <span className={item.v >= 0 ? "pos" : "neg"} style={{ width: `${(Math.abs(item.v) / max) * 50}%` }} />
          </div>
          <b>{item.v > 0 ? `+${item.v.toFixed(0)}` : item.v.toFixed(0)}</b>
        </div>
      ))}
    </div>
  );
}

export function FormPills({ results }: { results: { result: string; opp: string; score: string }[] }) {
  if (!results.length) return <p className="muted">No finished games yet.</p>;
  return (
    <div className="pills">
      {results.map((row, i) => (
        <span key={i} className={`pill ${row.result}`} title={`${row.result} vs ${row.opp} (${row.score})`}>
          {row.result}
        </span>
      ))}
    </div>
  );
}

export function Metrics({ items }: { items: { label: string; value: string }[] }) {
  return (
    <div className="metrics">
      {items.map((item) => (
        <div className="metric" key={item.label}>
          <span>{item.label}</span>
          <b>{item.value}</b>
        </div>
      ))}
    </div>
  );
}
