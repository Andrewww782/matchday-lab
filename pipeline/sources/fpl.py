"""Fantasy Premier League public API (current season) + vaastav archive (past seasons)."""
import io

import pandas as pd

from pipeline.config import POSITIONS, canon_team
from pipeline.http import get_bytes, get_json

API = "https://fantasy.premierleague.com/api"
ARCHIVE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"

NUMERIC = [
    "minutes", "starts", "goals_scored", "assists", "clean_sheets", "goals_conceded",
    "saves", "bonus", "bps", "yellow_cards", "red_cards", "total_points",
    "influence", "creativity", "threat", "ict_index", "expected_goals",
    "expected_assists", "expected_goal_involvements", "expected_goals_conceded",
    "tackles", "clearances_blocks_interceptions", "recoveries", "defensive_contribution",
]


def bootstrap() -> dict:
    return get_json(f"{API}/bootstrap-static/", max_age_hours=6)


def teams() -> pd.DataFrame:
    t = pd.DataFrame(bootstrap()["teams"])[["id", "name", "short_name", "strength"]]
    t["team"] = t["name"].map(canon_team)
    return t.rename(columns={"id": "team_id"})


def events() -> pd.DataFrame:
    return pd.DataFrame(bootstrap()["events"])[
        ["id", "name", "deadline_time", "finished", "is_current", "is_next"]
    ]


def players() -> pd.DataFrame:
    """Current-season player list with season-to-date totals."""
    df = pd.DataFrame(bootstrap()["elements"])
    df = df[~df["removed"].astype(bool)] if "removed" in df else df
    for c in NUMERIC + ["form", "selected_by_percent", "ep_next", "points_per_game"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    t = teams().set_index("team_id")["team"]
    df["team"] = df["team"].map(t)
    df["pos"] = df["element_type"].map(POSITIONS)
    df["price"] = df["now_cost"] / 10
    df["birth_date"] = pd.to_datetime(df["birth_date"], errors="coerce")
    return df.rename(columns={"id": "fpl_id"})


def fixtures() -> pd.DataFrame:
    df = pd.DataFrame(get_json(f"{API}/fixtures/", max_age_hours=6))
    t = teams().set_index("team_id")["team"]
    df["home"] = df["team_h"].map(t)
    df["away"] = df["team_a"].map(t)
    df["kickoff"] = pd.to_datetime(df["kickoff_time"], utc=True, errors="coerce")
    return df[["id", "event", "kickoff", "home", "away", "team_h_score", "team_a_score",
               "finished", "team_h_difficulty", "team_a_difficulty"]]


def past_season_players(start_year: int) -> pd.DataFrame:
    """Season totals for a finished season from the vaastav archive, keyed by FPL `code`."""
    tag = f"{start_year}-{str(start_year + 1)[-2:]}"
    raw = pd.read_csv(io.BytesIO(get_bytes(f"{ARCHIVE}/{tag}/players_raw.csv", float("inf"))))
    tm = pd.read_csv(io.BytesIO(get_bytes(f"{ARCHIVE}/{tag}/teams.csv", float("inf"))))
    raw["team"] = raw["team"].map(tm.set_index("id")["name"]).map(canon_team)
    raw["pos"] = raw["element_type"].map(POSITIONS)
    keep = ["code", "first_name", "second_name", "web_name", "team", "pos"]
    cols = [c for c in NUMERIC if c in raw.columns]
    out = raw[keep + cols].copy()
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    return out


def entry_picks(entry_id: int, event: int) -> dict:
    """A manager's squad for a gameweek (public, no login). Used live by the app."""
    return get_json(f"{API}/entry/{entry_id}/event/{event}/picks/", max_age_hours=0.25)


def entry(entry_id: int) -> dict:
    return get_json(f"{API}/entry/{entry_id}/", max_age_hours=0.25)
