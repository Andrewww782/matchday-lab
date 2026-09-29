"""Transfermarkt snapshot from dcaribou/transfermarkt-datasets (valuations end 12 Jun 2026).

`team` is only reliable for English clubs; pipeline/clubs.py maps other clubs by shared players."""
import time

import duckdb
import pandas as pd

from pipeline.config import RAW, canon_team
from pipeline.http import _session

URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/transfermarkt-datasets.duckdb"
DB = RAW / "transfermarkt.duckdb"


def _db() -> duckdb.DuckDBPyConnection:
    # The dataset's pipeline is paused, so re-download at most monthly.
    if not DB.exists() or time.time() - DB.stat().st_mtime > 30 * 86400:
        try:
            with _session.get(URL, stream=True, timeout=300) as r:
                r.raise_for_status()
                tmp = DB.with_suffix(".part")
                with open(tmp, "wb") as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
                tmp.replace(DB)
        except Exception:
            if not DB.exists():
                raise
    return duckdb.connect(str(DB), read_only=True)


def players() -> pd.DataFrame:
    with _db() as c:
        df = c.sql("""
            select player_id as tm_id, name, date_of_birth, position, sub_position, foot,
                   height_in_cm, international_caps, contract_expiration_date,
                   current_club_name, current_club_domestic_competition_id as tm_comp,
                   market_value_in_eur, highest_market_value_in_eur
            from players
            where last_season >= '2022'
        """).df()
    df["team"] = df["current_club_name"].map(canon_team)
    df["date_of_birth"] = pd.to_datetime(df["date_of_birth"]).dt.normalize()
    return df


def valuations() -> pd.DataFrame:
    with _db() as c:
        df = c.sql("""
            select player_id as tm_id, date, market_value_in_eur as value, current_club_name,
                   player_club_domestic_competition_id as tm_comp
            from player_valuations where date >= '2022-01-01'
        """).df()
    df["date"] = pd.to_datetime(df["date"])
    df["team"] = df["current_club_name"].map(canon_team)
    return df


def snapshot_date() -> pd.Timestamp:
    with _db() as c:
        return pd.Timestamp(c.sql("select max(date) from player_valuations").fetchone()[0])
