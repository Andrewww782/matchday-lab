"""football-data.co.uk: historical results, shots and bookmaker odds."""
import io

import pandas as pd

from pipeline.config import CURRENT_SEASON, canon_team
from pipeline.http import get_bytes


def season(start_year: int) -> pd.DataFrame:
    code = f"{str(start_year)[-2:]}{str(start_year + 1)[-2:]}"
    age = 12 if start_year >= CURRENT_SEASON else float("inf")
    raw = get_bytes(f"https://www.football-data.co.uk/mmz4281/{code}/E0.csv", age)
    df = pd.read_csv(io.StringIO(raw.decode("latin1")))
    df.columns = [c.lstrip("﻿").lstrip("ï»¿") for c in df.columns]
    df = df.dropna(subset=["HomeTeam", "FTHG"])
    out = pd.DataFrame({
        "date": pd.to_datetime(df["Date"], format="mixed", dayfirst=True).dt.normalize(),
        "home": df["HomeTeam"].map(canon_team),
        "away": df["AwayTeam"].map(canon_team),
        "home_goals": df["FTHG"].astype(int),
        "away_goals": df["FTAG"].astype(int),
        "home_shots": df.get("HS"),
        "away_shots": df.get("AS"),
        "home_sot": df.get("HST"),
        "away_sot": df.get("AST"),
        "odds_h": df.get("B365H"),
        "odds_d": df.get("B365D"),
        "odds_a": df.get("B365A"),
    })
    out["season"] = start_year
    return out.reset_index(drop=True)
