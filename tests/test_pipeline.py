"""Checks on the pipeline outputs in data/ (no network needed)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.simulate import current_table, simulate

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture(scope="module")
def players():
    return pd.read_parquet(DATA / "players.parquet")


def test_cross_source_match_rates(players):
    played = players[players["cur_minutes"] > 0]
    assert played["understat_id"].notna().mean() >= 0.95
    assert played["tm_id"].notna().mean() >= 0.90  # promoted-club players often have no TM value


def test_no_player_linked_twice(players):
    for col in ["understat_id", "tm_id"]:
        linked = players[col].dropna()
        assert linked.is_unique, f"{col} assigned to more than one player"


def test_form_features_only_use_earlier_matches():
    long = pd.read_parquet(DATA / "team_matches.parquet").sort_values(["team", "date"])
    rng = np.random.default_rng(0)
    for i in rng.choice(len(long), 200, replace=False):
        row = long.iloc[i]
        prior = long[(long.team == row.team) & (long.stint == row.stint) & (long.date < row.date)].tail(5)
        expected = prior["xgf"].mean() if len(prior) >= 3 else np.nan
        if np.isnan(expected):
            assert np.isnan(row["xgf_5"])
        else:
            assert row["xgf_5"] == pytest.approx(expected)


def test_elo_is_pre_match():
    m = pd.read_parquet(DATA / "matches.parquet").sort_values("date")
    first = m[m.season == m.season.min()].head(10)
    assert (first["home_elo"] == 1500).all() and (first["away_elo"] == 1500).all()


def test_probabilities_sum_to_one():
    for name in ["pair_probs", "upcoming", "track_record"]:
        df = pd.read_parquet(DATA / f"{name}.parquet")
        assert np.allclose(df[["p_h", "p_d", "p_a"]].sum(axis=1), 1, atol=1e-6)


def test_per90_maths():
    sc = pd.read_parquet(DATA / "scout.parquet")
    p = pd.read_parquet(DATA / "players.parquet").set_index("code")
    r = sc.iloc[0]
    assert r["p90_npxG"] == pytest.approx(p.at[r["code"], "win_npxG"] / p.at[r["code"], "win_time"] * 90, rel=1e-3)


def test_simulator_all_home_wins_is_deterministic():
    fx = pd.read_parquet(DATA / "fixtures.parquet")
    teams = pd.read_parquet(DATA / "teams.parquet")["team"].tolist()
    table = current_table(fx, teams)
    rem = pd.read_parquet(DATA / "upcoming.parquet").set_index("fixture_id")
    res = simulate(table, rem, n=200, locked={i: "H" for i in rem.index})
    expected = table["Pts"] + 3 * rem["home"].value_counts().reindex(table.index, fill_value=0)
    assert np.allclose(res["summary"].loc[table.index, "exp_pts"], expected)
    assert np.allclose(res["positions"].sum(axis=1), 1)


def test_simulator_total_points_are_plausible():
    fx = pd.read_parquet(DATA / "fixtures.parquet")
    teams = pd.read_parquet(DATA / "teams.parquet")["team"].tolist()
    table = current_table(fx, teams)
    rem = pd.read_parquet(DATA / "upcoming.parquet").set_index("fixture_id")
    total = simulate(table, rem, n=2000)["summary"]["exp_pts"].sum()
    # 380 games; each is worth 3 points (win) or 2 (draw). ~25% draws -> ~1045 points.
    assert 990 < total < 1100
