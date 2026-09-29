"""Cached loaders for the artifacts the weekly pipeline writes to data/."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parents[1] / "data"
TTL = 3600  # artifacts only change when the weekly refresh redeploys the app
DEFAULT_LEAGUE = "EPL"


@st.cache_data(ttl=TTL)
def table(name: str) -> pd.DataFrame:
    return pd.read_parquet(DATA / f"{name}.parquet")


@st.cache_data(ttl=TTL)
def meta(name: str) -> dict:
    p = DATA / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def available(*names: str) -> bool:
    return all((DATA / f"{n}.parquet").exists() for n in names)


@st.cache_data(ttl=TTL)
def leagues() -> dict:
    """{key: {name, clubs, cl, relegated, playoff}} in display order (Premier League first)."""
    return meta("leagues") or {DEFAULT_LEAGUE: {"name": "Premier League", "clubs": 20, "cl": 4,
                                                "relegated": 3, "playoff": None}}


def league_name(key: str) -> str:
    return leagues().get(key, {}).get("name", key)


@st.cache_data(ttl=TTL)
def player_index() -> pd.DataFrame:
    """Everyone who has played in Europe's top 5 leagues this season or last, for search boxes.
    Labels are "Name · Club" (they appear in shareable URLs, so they must stay stable)."""
    p = table("players")
    p = p[(p["win_time"] > 0)].copy()
    p["label"] = p["name"] + " · " + p["team"]
    dupes = p["label"].duplicated(keep=False)
    p.loc[dupes, "label"] = p.loc[dupes, "label"] + " (" + p.loc[dupes, "league_name"] + ")"
    return p.sort_values("win_time", ascending=False)[
        ["pid", "name", "web_name", "team", "league", "league_name", "pos", "label", "age", "tm_value"]]


def player_label(pid: int) -> str:
    return player_index().set_index("pid")["label"].get(pid, str(pid))


@st.cache_data(ttl=TTL)
def teams(league: str | None = None) -> list[str]:
    t = table("teams")
    if league:
        t = t[t["league"] == league]
    return sorted(t["team"].tolist())


@st.cache_data(ttl=TTL)
def team_league() -> dict:
    return table("teams").set_index("team")["league"].to_dict()


@st.cache_data(ttl=TTL)
def short_names() -> dict:
    return table("teams").set_index("team")["short_name"].to_dict()


@st.cache_data(ttl=TTL)
def club_colours() -> dict:
    t = table("teams")
    return t.set_index("team")["colour"].to_dict() if "colour" in t else {}
