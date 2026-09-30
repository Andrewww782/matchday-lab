"""Fan VAR incident parser, checked on real ESPN match summaries saved in tests/fixtures/espn/."""
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from pipeline import build_incidents as bi

FIX = Path(__file__).parent / "fixtures" / "espn"


def calls(league: str, event_id: str, score=(0, 0)) -> pd.DataFrame:
    s = json.loads((FIX / f"{league}_{event_id}.json").read_text(encoding="utf-8"))
    home, away = (r["team"]["displayName"] for r in s["rosters"][:2])
    ev = SimpleNamespace(event_id=event_id, home_raw=home, away_raw=away, kickoff=pd.Timestamp("2026-09-20", tz="UTC"),
                         home_goals=score[0], away_goals=score[1])
    names = {home: home, away: away}
    return pd.DataFrame(bi.match_incidents(league, ev, s, names, {"gw": 5})), home, away


def test_madrid_derby_card_upgrades_and_penalty():
    df, home, away = calls("La_Liga", "401882865", (2, 1))
    big = df[df.big]
    assert list(big.kind) == ["var_red", "var_red"]
    pen = big.iloc[1]
    assert "Penalty and red card" in pen.headline and "Huijsen" in pen.headline and "scored" in pen.headline
    assert pen.against_team == "Real Madrid" and pen.benefit_team is not None
    assert "Romero" in big.iloc[0].headline
    # grouped: the foul, the VAR check, the red and the penalty goal are one call
    assert pen.lines.count("\n") >= 3


def test_goal_overturned_by_var():
    df, home, away = calls("Bundesliga", "401884788", (2, 0))
    o = df[df.kind == "goal_overturned"]
    assert len(o) == 1 and "Nkunku" in o.iloc[0].headline and o.iloc[0].against_team == away
    assert o.iloc[0].given == "No goal" and o.iloc[0].options == "Goal|No goal"


def test_second_yellow_is_a_red():
    df, home, away = calls("Ligue_1", "401876449", (1, 2))
    r = df[df.kind == "red"]
    assert len(r) == 1 and "Second yellow" in r.iloc[0].headline and "Weah" in r.iloc[0].headline
    assert r.iloc[0].against_team == home


def test_goal_confirmed_by_var_goes_against_the_other_side():
    df, home, away = calls("EPL", "401879272", (5, 3))
    g = df[df.kind == "goal_stands"]
    assert len(g) == 2
    by_player = dict(zip(g.player, g.against_team))
    assert by_player["Erling Haaland"] == away and by_player["Brian Brobbey"] == home


def test_yellows_are_small_calls_and_ids_are_unique():
    for f in FIX.glob("*.json"):
        league, eid = f.stem.rsplit("_", 1)
        df, *_ = calls(league, eid)
        assert df.incident_id.is_unique
        assert not df[df.kind == "yellow"].big.any()
        assert set(df.kind) <= set(bi.OPTIONS)
        for r in df.itertuples():
            assert r.given in r.options.split("|") or r.kind == "var_other"


@pytest.mark.skipif(not (Path(__file__).parents[1] / "data" / "incidents.parquet").exists(), reason="no built data")
def test_built_incidents_cover_every_league():
    inc = pd.read_parquet(Path(__file__).parents[1] / "data" / "incidents.parquet")
    m = pd.read_parquet(Path(__file__).parents[1] / "data" / "var_matches.parquet")
    assert set(inc[inc.big].league) == {"EPL", "La_Liga", "Serie_A", "Bundesliga", "Ligue_1"}
    assert inc.gw.notna().all() and m.gw.notna().all()  # every ESPN match found its fixture
    fx = pd.read_parquet(Path(__file__).parents[1] / "data" / "fixtures.parquet")
    ours = set(fx.home) | set(fx.away)
    assert set(m.home) | set(m.away) <= ours  # ESPN club names all mapped to ours


def test_highlights_pick_trusts_only_official_channels():
    from pipeline import build_highlights as bh

    def item(vid, title, channel):
        return {"id": {"videoId": vid}, "snippet": {"title": title, "channelTitle": channel}}
    items = [item("a", "Man City v Sunderland | Every goal reacted", "Random Fan TV"),
             item("b", "Man City 5-3 Sunderland | Extended press conference", "Premier League"),
             item("c", "HIGHLIGHTS | Man City 5-3 Sunderland | Haaland seals it", "Premier League")]
    assert bh.pick(items, "EPL", "Man City", "Sunderland")["video_id"] == "c"
    assert bh.pick(items[:1], "EPL", "Man City", "Sunderland") is None
    assert bh.pick([item("d", "Resumen: Valencia 2-3 Real Sociedad", "LALIGA EA SPORTS")], "La_Liga",
                   "Valencia", "Real Sociedad")["video_id"] == "d"
    assert bh.pick([item("e", "Valencia highlights", "LALIGA EA SPORTS")], "La_Liga", "Valencia", "Real Sociedad") is None


def test_highlights_step_skips_without_a_key(monkeypatch, capsys):
    from pipeline import build_highlights as bh
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    bh.main()
    assert "skipping" in capsys.readouterr().out
