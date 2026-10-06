import type { Metadata } from "next";
import { LeagueBar } from "@/components/Bits";
import { highlights, incidents, resolveLeague, site, varMatches } from "@/lib/data";
import { href, KIND_LABEL, streamlit, whenUK } from "@/lib/format";

export const metadata: Metadata = { title: "Fan VAR" };

export default async function VarPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const league = resolveLeague(sp);
  const info = site().leagues[league];
  const theName = league === "EPL" ? `the ${info.name}` : info.name;
  const matches = varMatches()
    .filter((row) => row.league === league)
    .sort((a, b) => (b.kickoff ?? "").localeCompare(a.kickoff ?? ""));
  const rounds = [...new Set(matches.map((row) => row.gw).filter((gw): gw is number => gw != null))].sort((a, b) => b - a);
  const askedGw = Number(sp.gw);
  const gw = rounds.includes(askedGw) ? askedGw : rounds[0];
  const calls = incidents()
    .filter((row) => row.league === league && row.gw === gw && row.big)
    .sort((a, b) => (b.kickoff ?? "").localeCompare(a.kickoff ?? "") || (a.seconds ?? 0) - (b.seconds ?? 0));
  const eventId = typeof sp.event === "string" && matches.some((row) => row.eventId === sp.event) ? sp.event : matches[0]?.eventId;
  const match = matches.find((row) => row.eventId === eventId);
  const mine = incidents()
    .filter((row) => row.eventId === eventId)
    .sort((a, b) => (a.seconds ?? 0) - (b.seconds ?? 0));
  const video = eventId ? highlights()[eventId] : undefined;
  const voteHref = streamlit("/var", { league });

  return (
    <>
      <p className="hero-tag">
        <span className="sticker">You&apos;re the VAR</span>
      </p>
      <h1>
        Fan <em>VAR</em>
      </h1>
      <p className="lede">
        Every big refereeing call in {theName}: penalties, red cards, VAR checks and goals ruled out.
        Watch the official highlights, then give your verdict on the Streamlit app. One vote per call per device.
      </p>
      <LeagueBar league={league} path="/var" keep={{ gw: gw ? String(gw) : undefined, event: eventId }} />

      <p className="note">
        Live vote totals, fan flags and the referee report card stay on the Streamlit app, which is still open.{" "}
        <a href={voteHref}>Vote on footyminds.streamlit.app/var</a>.
      </p>

      <section>
        <div className="eyebrow">Big calls</div>
        <h2>
          {info.round} {gw}
        </h2>
        <form className="filters" action="/var">
          <input type="hidden" name="league" value={league} />
          {eventId ? <input type="hidden" name="event" value={eventId} /> : null}
          <label>
            {info.round}
            <select name="gw" defaultValue={String(gw)}>
              {rounds.map((round) => (
                <option key={round} value={round}>
                  {info.round} {round}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">Show round</button>
        </form>
        {calls.length ? (
          <div className="grid-2">
            {calls.map((call) => (
              <article className="card" key={call.id}>
                <span className="sticker">{KIND_LABEL[call.kind] ?? "Call"}</span>
                <h3>{call.headline}</h3>
                <p className="muted">
                  {call.home} {call.score} {call.away}
                  {call.minute != null ? ` · ${call.minute}'` : ""}
                  {call.player ? ` · ${call.player}` : ""}
                </p>
                <a className="btn" href={voteHref}>
                  Right or wrong?
                </a>
              </article>
            ))}
          </div>
        ) : (
          <p className="note">No big calls in {info.round} {gw}. The refs had a quiet week.</p>
        )}
      </section>

      <section>
        <div className="eyebrow">Every match</div>
        <h2>Cards, penalties and VAR</h2>
        <form className="filters" action="/var">
          <input type="hidden" name="league" value={league} />
          {gw ? <input type="hidden" name="gw" value={gw} /> : null}
          <label>
            Match
            <select name="event" defaultValue={eventId}>
              {matches.map((row) => (
                <option key={row.eventId} value={row.eventId}>
                  {whenUK(row.kickoff)} · {row.home} {row.score} {row.away}
                </option>
              ))}
            </select>
          </label>
          <button type="submit">Show match</button>
        </form>
        {match?.referee ? <p className="muted">Referee: {match.referee}</p> : null}
        {video ? (
          <div className="video">
            <iframe
              src={`https://www.youtube.com/embed/${video.videoId}`}
              title={video.title ?? "Match highlights"}
              allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
              allowFullScreen
            />
          </div>
        ) : (
          <p className="muted">No official highlights filed for this match yet.</p>
        )}
        <div className="grid-2">
          {mine.map((call) => (
            <article className="card" key={call.id}>
              <span className={`sticker ${call.kind === "yellow" ? "lime" : ""}`}>{KIND_LABEL[call.kind] ?? "Call"}</span>
              <h3>{call.headline}</h3>
              <p className="muted">
                {call.minute != null ? `${call.minute}'` : ""}
                {call.player ? ` · ${call.player}` : ""}
                {call.given ? ` · given: ${call.given}` : ""}
              </p>
            </article>
          ))}
        </div>
        {mine.length === 0 ? <p className="note">No cards, penalties or VAR checks in this one.</p> : null}
      </section>
    </>
  );
}
