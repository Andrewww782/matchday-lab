"""Cached loaders for the artifacts the weekly pipeline writes to data/."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

DATA = Path(__file__).resolve().parents[1] / "data"
TTL = 3600  # artifacts only change when the weekly refresh redeploys the app


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
def player_index() -> pd.DataFrame:
    """Everyone who has played this season or last, for search boxes."""
    p = table("players")
    p = p[(p["win_minutes"] > 0)].copy()
    p["label"] = p["name"] + " · " + p["team"]
    return p.sort_values("win_minutes", ascending=False)[
        ["code", "name", "web_name", "team", "pos", "label", "age", "price", "tm_value"]]


def player_label(code: int) -> str:
    idx = player_index().set_index("code")["label"]
    return idx.get(code, str(code))


@st.cache_data(ttl=TTL)
def teams() -> list[str]:
    return sorted(table("teams")["team"].tolist())


@st.cache_data(ttl=TTL)
def short_names() -> dict:
    return table("teams").set_index("team")["short_name"].to_dict()
