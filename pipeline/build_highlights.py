"""Find each finished match's official highlights on YouTube, for the Fan VAR page.

Uses the YouTube Data API (free: 10,000 units a day; one search costs 100). Needs YOUTUBE_API_KEY
in the environment (a GitHub Actions secret); without it this step does nothing and the app shows a
"search the highlights" link instead. Only official league (or rights-holder) channels count, and the
video title has to name both clubs. Each match is searched at most 3 times, in its first week."""
import os

import pandas as pd
import requests

from pipeline.config import DATA
from pipeline.matching import norm

API = "https://www.googleapis.com/youtube/v3/search"
# Channel titles we trust per league (compared after normalising: lower case, no accents/punctuation).
CHANNELS = {
    "EPL": ["premier league", "nbc sports", "sky sports football", "sky sports premier league"],
    "La_Liga": ["laliga ea sports", "laliga", "laliga santander"],
    "Serie_A": ["serie a"],
    "Bundesliga": ["bundesliga"],
    "Ligue_1": ["ligue 1 mcdonald s", "ligue 1", "ligue 1 uber eats"],
}
MAX_TRIES, SEARCH_DAYS = 3, 7


def _tokens(club: str) -> set[str]:
    """Words that identify a club in a video title ("Man City" -> {"man", "city"}; short words dropped)."""
    return {w for w in norm(club).split() if len(w) >= 3 and w not in {"fc", "cf", "ac", "afc", "sc", "the"}}


def pick(items: list[dict], league: str, home: str, away: str) -> dict | None:
    """The first video from a trusted channel whose title names both clubs, preferring "highlights"."""
    ok = []
    for it in items:
        sn = it.get("snippet", {})
        words = set(norm(sn.get("title", "")).split())
        if norm(sn.get("channelTitle", "")) in CHANNELS[league] and _tokens(home) & words and _tokens(away) & words:
            ok.append((not ({"highlights", "highlight"} & words), it))
    if not ok:
        return None
    it = sorted(ok, key=lambda x: x[0])[0][1]
    return {"video_id": it["id"]["videoId"], "title": it["snippet"].get("title"), "channel": it["snippet"].get("channelTitle")}


def search(key: str, league: str, home: str, away: str, kickoff: pd.Timestamp) -> dict | None:
    r = requests.get(API, timeout=30, params={
        "part": "snippet", "type": "video", "videoEmbeddable": "true", "maxResults": 10, "key": key,
        "q": f"{home} vs {away} highlights",
        "publishedAfter": kickoff.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "publishedBefore": (kickoff + pd.Timedelta(days=SEARCH_DAYS)).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
    })
    r.raise_for_status()
    return pick(r.json().get("items", []), league, home, away)


def main():
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("  YOUTUBE_API_KEY not set: skipping (the app links to a YouTube search instead)")
        return
    path = DATA / "highlights.parquet"
    cols = ["event_id", "video_id", "title", "channel", "tries", "searched_at"]
    have = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=cols)
    matches = pd.read_parquet(DATA / "var_matches.parquet")
    now = pd.Timestamp.now(tz="UTC")
    rows = {r.event_id: r._asdict() for r in have.itertuples(index=False)}
    found = searched = 0
    for m in matches.sort_values("kickoff", ascending=False).itertuples():
        prev = rows.get(m.event_id, {})
        if prev.get("video_id") or prev.get("tries", 0) >= MAX_TRIES:
            continue
        if now - m.kickoff > pd.Timedelta(days=SEARCH_DAYS + 1) and prev:
            continue  # already tried while it was fresh
        try:
            hit = search(key, m.league, m.home, m.away, m.kickoff)
        except requests.HTTPError as e:
            print(f"  YouTube search stopped: {e}")  # usually the daily quota; carry on tomorrow
            break
        searched += 1
        found += bool(hit)
        rows[m.event_id] = {"event_id": m.event_id, **(hit or {"video_id": None, "title": None, "channel": None}),
                            "tries": prev.get("tries", 0) + 1, "searched_at": now}
    out = pd.DataFrame(list(rows.values()), columns=cols)
    out.to_parquet(path, index=False)
    print(f"  searched {searched} matches, found {found}; {out.video_id.notna().sum()} matches have highlights")


if __name__ == "__main__":
    main()
