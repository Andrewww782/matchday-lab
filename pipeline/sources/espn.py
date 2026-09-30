"""ESPN's public match feed: per-match commentary, key events, line-ups and the referee.

It's the only free source with refereeing detail for all five leagues: cards with reasons, penalties,
and VAR outcomes ("VAR Decision: Card upgraded …", "GOAL OVERTURNED BY VAR: …"). Unofficial and
key-less, so we fetch politely through the disk cache: finished matches are cached forever."""
import pandas as pd

from pipeline.config import CURRENT_SEASON
from pipeline.http import get_json

SLUGS = {"EPL": "eng.1", "La_Liga": "esp.1", "Serie_A": "ita.1", "Bundesliga": "ger.1", "Ligue_1": "fra.1"}
BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
# ESPN only answers a few client types (browser-looking or custom agents get 403).
UA = "python-requests/2.32 (footyminds pipeline)"


def _months(start: pd.Timestamp, end: pd.Timestamp) -> list[str]:
    return [p.strftime("%Y%m") for p in pd.period_range(start, end, freq="M")]


def scoreboard(league: str, season: int = CURRENT_SEASON, until: pd.Timestamp | None = None) -> pd.DataFrame:
    """Every match of the season so far: event id, kick-off, ESPN club names, score, status."""
    until = until or pd.Timestamp.now(tz="UTC")
    now_month = until.strftime("%Y%m")
    rows = []
    for month in _months(pd.Timestamp(f"{season}-07-01"), until.tz_localize(None) if until.tzinfo else until):
        # Past months never change; the current month is re-read every few hours.
        age = 3 if month == now_month else float("inf")
        d = get_json(f"{BASE}/{SLUGS[league]}/scoreboard?dates={month}&limit=300", age, UA)
        for e in d.get("events", []):
            comp = e["competitions"][0]
            teams = {c["homeAway"]: c for c in comp["competitors"]}
            rows.append({
                "event_id": str(e["id"]), "league": league, "kickoff": pd.Timestamp(e["date"]),
                "home_raw": teams["home"]["team"]["displayName"], "away_raw": teams["away"]["team"]["displayName"],
                "home_goals": pd.to_numeric(teams["home"].get("score"), errors="coerce"),
                "away_goals": pd.to_numeric(teams["away"].get("score"), errors="coerce"),
                "state": e["status"]["type"]["state"],  # pre / in / post
                "completed": bool(e["status"]["type"].get("completed")),
            })
    df = pd.DataFrame(rows).drop_duplicates("event_id")
    return df.sort_values("kickoff").reset_index(drop=True)


def summary(league: str, event_id: str, finished: bool) -> dict:
    """The full match summary. Finished matches are cached forever."""
    return get_json(f"{BASE}/{SLUGS[league]}/summary?event={event_id}", float("inf") if finished else 1, UA)
