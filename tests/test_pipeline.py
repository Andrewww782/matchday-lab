"""Checks on the pipeline outputs in data/ (no network needed).

Tests on data/build/ (big intermediate tables that aren't committed) skip when it's absent."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.simulate import current_table, simulate

DATA = Path(__file__).resolve().parents[1] / "data"
BUILD = DATA / "build"
LEAGUES = json.loads((DATA / "leagues.json").read_text())


def build_table(name: str) -> pd.DataFrame:
    p = BUILD / f"{name}.parquet"
    if not p.exists():
        pytest.skip(f"{p.name} not built here (run the pipeline)")
    return pd.read_parquet(p)


@pytest.fixture(scope="module")
def players():
    return pd.read_parquet(DATA / "players.parquet")


@pytest.fixture(scope="module")
def teams():
    return pd.read_parquet(DATA / "teams.parquet")


def test_every_league_has_the_right_clubs(teams):
    counts = teams.groupby("league").size().to_dict()
    assert counts == {k: v["clubs"] for k, v in LEAGUES.items()}
    assert teams["team"].is_unique, "club names are used as keys, so they must be unique"
    assert (teams["colour"] != "#888888").all(), "every club needs a colour in app/clubs.csv"


def test_every_fixture_uses_known_clubs(teams):
    fx = pd.read_parquet(DATA / "fixtures.parquet")
    known = set(teams["team"])
    assert set(fx["home"]) <= known and set(fx["away"]) <= known
    per_league = fx.groupby("league").size().to_dict()
    assert per_league == {k: v["clubs"] * (v["clubs"] - 1) for k, v in LEAGUES.items()}


def test_all_historical_matches_have_mapped_clubs():
    m = build_table("matches")
    assert m["home"].notna().all() and m["away"].notna().all()
    assert set(m["league"]) == set(LEAGUES)


@pytest.mark.parametrize("league", list(LEAGUES))
def test_transfermarkt_match_rate(players, league):
    regular = players[(players["league"] == league) & (players["win_time"] >= 450)]
    assert len(regular) > 150
    assert regular["tm_id"].notna().mean() >= 0.85


def test_epl_fpl_links():
    epl = build_table("epl_players")
    played = epl[epl["cur_minutes"] > 0]
    assert played["understat_id"].notna().mean() >= 0.95
    assert played["tm_id"].notna().mean() >= 0.90  # promoted-club players often have no TM value


def test_no_player_linked_twice(players):
    assert players["pid"].is_unique
    assert players["tm_id"].dropna().is_unique


def test_form_features_only_use_earlier_matches():
    long = build_table("team_matches").sort_values(["team", "date"])
    rng = np.random.default_rng(0)
    for i in rng.choice(len(long), 300, replace=False):
        row = long.iloc[i]
        prior = long[(long.team == row.team) & (long.stint == row.stint) & (long.date < row.date)].tail(5)
        expected = prior["xgf"].mean() if len(prior) >= 3 else np.nan
        if np.isnan(expected):
            assert np.isnan(row["xgf_5"])
        else:
            assert row["xgf_5"] == pytest.approx(expected)


def test_elo_is_pre_match():
    m = build_table("matches").sort_values("date")
    for _, g in m.groupby("league"):
        first = g[g.season == g.season.min()].head(8)
        assert (first["home_elo"] == 1500).all() and (first["away_elo"] == 1500).all()


def test_probabilities_sum_to_one():
    for name in ["pair_probs", "upcoming", "track_record"]:
        df = pd.read_parquet(DATA / f"{name}.parquet")
        assert np.allclose(df[["p_h", "p_d", "p_a"]].sum(axis=1), 1, atol=1e-6)
        assert set(df["league"]) == set(LEAGUES)


def test_pairings_stay_within_a_league():
    pairs = pd.read_parquet(DATA / "pair_probs.parquet")
    lg = pd.read_parquet(DATA / "teams.parquet").set_index("team")["league"]
    assert (pairs["home"].map(lg) == pairs["away"].map(lg)).all()
    assert len(pairs) == sum(v["clubs"] * (v["clubs"] - 1) for v in LEAGUES.values())


def test_per90_maths(players):
    sc = pd.read_parquet(DATA / "scout.parquet")
    p = players.set_index("pid")
    for _, r in sc.sample(20, random_state=1).iterrows():
        assert r["p90_npxG"] == pytest.approx(p.at[r["pid"], "win_npxG"] / p.at[r["pid"], "win_time"] * 90, abs=1e-3)


def test_defensive_stats_only_claimed_for_premier_league():
    sc = pd.read_parquet(DATA / "scout.parquet")
    others = sc[sc["league"] != "EPL"]
    assert others["p90_tackles"].isna().all()
    assert (others["pos"] != "GK").all()
    assert (others["profile"] == "attacking").all()


def _league_sim(league, **kw):
    fx = pd.read_parquet(DATA / "fixtures.parquet").query("league == @league")
    teams = sorted(pd.read_parquet(DATA / "teams.parquet").query("league == @league")["team"])
    table = current_table(fx, teams)
    rem = pd.read_parquet(DATA / "upcoming.parquet").query("league == @league").set_index("fixture_id")
    r = LEAGUES[league]
    return table, rem, simulate(table, rem, cl=r["cl"], relegated=r["relegated"], playoff=r["playoff"], **kw)


def test_simulator_all_home_wins_is_deterministic():
    fx = pd.read_parquet(DATA / "upcoming.parquet").query("league == 'EPL'")
    table, rem, res = _league_sim("EPL", n=200, locked={i: "H" for i in fx["fixture_id"]})
    expected = table["Pts"] + 3 * rem["home"].value_counts().reindex(table.index, fill_value=0)
    assert np.allclose(res["summary"].loc[table.index, "exp_pts"], expected)
    assert np.allclose(res["positions"].sum(axis=1), 1)


@pytest.mark.parametrize("league", list(LEAGUES))
def test_simulator_totals_and_bands(league):
    table, rem, res = _league_sim(league, n=2000)
    s = res["summary"]
    games = LEAGUES[league]["clubs"] * (LEAGUES[league]["clubs"] - 1)
    # Each game is worth 3 points (win) or 2 (draw); ~25% draws -> ~2.75 points per game.
    assert 2.6 * games < s["exp_pts"].sum() < 2.9 * games
    assert s["cl"].sum() == pytest.approx(LEAGUES[league]["cl"], abs=1e-6)
    assert s["relegated"].sum() == pytest.approx(LEAGUES[league]["relegated"], abs=1e-6)
    if LEAGUES[league]["playoff"]:
        assert s["playoff"].sum() == pytest.approx(1, abs=1e-6)
