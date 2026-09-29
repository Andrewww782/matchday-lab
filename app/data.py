"""Cached loaders for the artifacts the weekly pipeline writes to data/.

Every cache is keyed on the data version (the newest file time in data/), so when a refresh
lands, nothing is served from the previous week's cache. Without this, a running server can mix
new code with old cached data after a deploy."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parents[1] / "data"
TTL = 3600
DEFAULT_LEAGUE = "EPL"


def version() -> int:
    """Changes whenever any artifact in data/ changes (cheap: a couple of dozen stat calls)."""
    return max((p.stat().st_mtime_ns for p in DATA.glob("*.*") if p.suffix in (".parquet", ".json")),
               default=0)


@st.cache_data(ttl=TTL, max_entries=64)
def _table(name: str, v: int) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"{name}.parquet")


def table(name: str) -> pd.DataFrame:
    return _table(name, version())


@st.cache_data(ttl=TTL, max_entries=64)
def _meta(name: str, v: int) -> dict:
    p = DATA / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def meta(name: str) -> dict:
    return _meta(name, version())


def available(*names: str) -> bool:
    return all((DATA / f"{n}.parquet").exists() for n in names)


def leagues() -> dict:
    """{key: {name, clubs, cl, relegated, playoff}} in display order (Premier League first)."""
    return meta("leagues") or {DEFAULT_LEAGUE: {"name": "Premier League", "clubs": 20, "cl": 4,
                                                "relegated": 3, "playoff": None}}


def league_name(key: str) -> str:
    return leagues().get(key, {}).get("name", key)


@st.cache_data(ttl=TTL, max_entries=8)
def _player_index(v: int) -> pd.DataFrame:
    p = table("players")
    p = p[(p["win_time"] > 0)].copy()
    p["label"] = p["name"] + " · " + p["team"]
    dupes = p["label"].duplicated(keep=False)
    p.loc[dupes, "label"] = p.loc[dupes, "label"] + " (" + p.loc[dupes, "league_name"] + ")"
    return p.sort_values("win_time", ascending=False)[
        ["pid", "name", "web_name", "team", "league", "league_name", "pos", "label", "age", "tm_value"]]


def player_index() -> pd.DataFrame:
    """Everyone who has played in Europe's top 5 leagues this season or last, for search boxes.
    Labels are "Name · Club" (they appear in shareable URLs, so they must stay stable)."""
    return _player_index(version())


def player_label(pid: int) -> str:
    return player_index().set_index("pid")["label"].get(pid, str(pid))


def teams(league: str | None = None) -> list[str]:
    t = table("teams")
    if league:
        t = t[t["league"] == league]
    return sorted(t["team"].tolist())


def team_league() -> dict:
    return table("teams").set_index("team")["league"].to_dict()


def short_names() -> dict:
    return table("teams").set_index("team")["short_name"].to_dict()


def club_colours() -> dict:
    t = table("teams")
    return t.set_index("team")["colour"].to_dict() if "colour" in t else {}
