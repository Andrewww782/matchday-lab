"""Understat: per-season player xG detail and per-match xG."""
import pandas as pd
from understatapi import UnderstatClient

from pipeline.config import CURRENT_SEASON, canon_team
from pipeline.http import cached_json

PLAYER_NUM = ["games", "time", "goals", "xG", "assists", "xA", "shots", "key_passes",
              "npg", "npxG", "xGChain", "xGBuildup"]


def _age(season: int) -> float:
    return 12 if season >= CURRENT_SEASON else float("inf")


def players(season: int) -> pd.DataFrame:
    def fetch():
        with UnderstatClient() as u:
            return u.league(league="EPL").get_player_data(season=str(season))

    df = pd.DataFrame(cached_json(f"understat:players:{season}", fetch, _age(season)))
    for c in PLAYER_NUM:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    # Mid-season movers are listed as "Old Club,New Club"; the last one is current.
    df["team"] = df["team_title"].str.split(",").str[-1].map(canon_team)
    df["season"] = season
    return df.rename(columns={"id": "understat_id", "player_name": "name"})


def matches(season: int) -> pd.DataFrame:
    def fetch():
        with UnderstatClient() as u:
            return u.league(league="EPL").get_match_data(season=str(season))

    rows = []
    for m in cached_json(f"understat:matches:{season}", fetch, _age(season)):
        if not m.get("isResult"):
            continue
        rows.append({
            "date": pd.Timestamp(m["datetime"]).normalize(),
            "home": canon_team(m["h"]["title"]),
            "away": canon_team(m["a"]["title"]),
            "home_xg": float(m["xG"]["h"]),
            "away_xg": float(m["xG"]["a"]),
            "season": season,
        })
    return pd.DataFrame(rows)
