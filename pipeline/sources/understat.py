"""Understat: per-season player xG detail, per-match xG and the full season schedule.

Understat is the reference source for club names outside England (see pipeline/clubs.py)."""
import pandas as pd
from understatapi import UnderstatClient

from pipeline.config import CURRENT_SEASON, display_team
from pipeline.http import cached_json

PLAYER_NUM = ["games", "time", "goals", "xG", "assists", "xA", "shots", "key_passes",
              "npg", "npxG", "xGChain", "xGBuildup"]


def _age(season: int) -> float:
    return 12 if season >= CURRENT_SEASON else float("inf")


def _key(kind: str, season: int, league: str) -> str:
    # Premier League keys predate multi-league support; keep them so caches stay valid.
    return f"understat:{kind}:{season}" if league == "EPL" else f"understat:{league}:{kind}:{season}"


def players(season: int, league: str = "EPL") -> pd.DataFrame:
    def fetch():
        with UnderstatClient() as u:
            return u.league(league=league).get_player_data(season=str(season))

    df = pd.DataFrame(cached_json(_key("players", season, league), fetch, _age(season)))
    for c in PLAYER_NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    # Mid-season movers are listed as "Old Club,New Club"; the last one is current.
    df["team"] = df["team_title"].str.split(",").str[-1].map(lambda t: display_team(league, t))
    df["season"] = season
    df["league"] = league
    return df.rename(columns={"id": "understat_id", "player_name": "name"})


def _raw_matches(season: int, league: str) -> list[dict]:
    def fetch():
        with UnderstatClient() as u:
            return u.league(league=league).get_match_data(season=str(season))

    return cached_json(_key("matches", season, league), fetch, _age(season))


def fixtures(season: int, league: str = "EPL") -> pd.DataFrame:
    """Every match of the season, played or not."""
    rows = []
    for m in _raw_matches(season, league):
        played = bool(m.get("isResult"))
        rows.append({
            "understat_match_id": int(m["id"]),
            "kickoff": pd.Timestamp(m["datetime"], tz="UTC"),
            "date": pd.Timestamp(m["datetime"]).normalize(),
            "home": display_team(league, m["h"]["title"]),
            "away": display_team(league, m["a"]["title"]),
            "home_short": m["h"].get("short_title"),
            "away_short": m["a"].get("short_title"),
            "finished": played,
            "home_goals": int(m["goals"]["h"]) if played else None,
            "away_goals": int(m["goals"]["a"]) if played else None,
            "home_xg": float(m["xG"]["h"]) if played and m["xG"]["h"] is not None else None,
            "away_xg": float(m["xG"]["a"]) if played and m["xG"]["a"] is not None else None,
            "season": season,
            "league": league,
        })
    return pd.DataFrame(rows)


def matches(season: int, league: str = "EPL") -> pd.DataFrame:
    """Played matches only."""
    f = fixtures(season, league)
    return f[f["finished"]].reset_index(drop=True)
