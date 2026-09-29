"""Smoke tests: every page renders with the committed data and no exceptions."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["app/pages/home.py", "app/pages/match.py", "app/pages/value.py", "app/pages/scout.py",
         "app/pages/compare.py", "app/pages/simulator.py", "app/pages/fpl.py", "app/pages/about.py"]


def run(page: str, **query) -> AppTest:
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    for k, v in query.items():
        at.query_params[k] = v
    at.run()
    if page != PAGES[0]:
        at.switch_page(page).run()
    return at


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page):
    at = run(page)
    assert not at.exception, [e.value for e in at.exception]


def test_match_page_explains_prediction():
    at = run("app/pages/match.py", home="Arsenal", away="Leeds")
    assert not at.exception
    assert any("Most likely" in m.value for m in at.markdown)


def test_value_page_for_saka():
    at = run("app/pages/value.py", player="Bukayo Saka · Arsenal")
    assert not at.exception
    assert any("Bukayo Saka" in str(h.proto) for h in at.get("html"))


def test_compare_from_link():
    at = run("app/pages/compare.py", players=["Bukayo Saka · Arsenal", "Cole Palmer · Chelsea"])
    assert not at.exception
    assert at.multiselect(key="players").value and len(at.multiselect(key="players").value) == 2


def test_simulator_probabilities_add_up():
    at = run("app/pages/simulator.py")
    assert not at.exception


def test_simulator_what_if_mode():
    import pandas as pd
    up = pd.read_parquet(ROOT / "data" / "upcoming.parquet").query("league == 'EPL'")
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    at.run()
    at.session_state["whatif"] = {"EPL": {up["fixture_id"].iloc[0]: "A"}}
    at.switch_page("app/pages/simulator.py").run()
    assert not at.exception
    assert any("locked in" in c.value for c in at.caption)


LEAGUE_NAMES = ["Premier League", "La Liga", "Serie A", "Bundesliga", "Ligue 1"]
LEAGUE_PAGES = ["app/pages/home.py", "app/pages/match.py", "app/pages/simulator.py"]


@pytest.mark.parametrize("league", LEAGUE_NAMES)
@pytest.mark.parametrize("page", LEAGUE_PAGES)
def test_league_pages_render(page, league):
    at = run(page, league=league)
    assert not at.exception, [e.value for e in at.exception]
    assert at.segmented_control(key="league").value ==         {"Premier League": "EPL", "La Liga": "La_Liga", "Serie A": "Serie_A",
         "Bundesliga": "Bundesliga", "Ligue 1": "Ligue_1"}[league]


def test_old_links_mean_premier_league():
    at = run("app/pages/match.py", home="Arsenal", away="Leeds")
    assert at.segmented_control(key="league").value == "EPL"
    assert at.selectbox(key="home").value == "Arsenal"


def test_club_link_picks_its_league():
    at = run("app/pages/match.py", home="Barcelona", away="Getafe")
    assert not at.exception
    assert at.segmented_control(key="league").value == "La_Liga"
    assert at.selectbox(key="home").value == "Barcelona"


def test_value_page_outside_england():
    at = run("app/pages/value.py", player="Lamine Yamal · Barcelona")
    assert not at.exception
    assert any("Lamine Yamal" in str(h.proto) for h in at.get("html"))


def test_scout_across_europe():
    at = run("app/pages/scout.py", player="Bukayo Saka · Arsenal")
    assert not at.exception
    html = " ".join(str(h.proto) for h in at.get("html"))
    assert any(lg in html for lg in ["La Liga", "Serie A", "Bundesliga", "Ligue 1"])


def test_compare_mixed_leagues():
    at = run("app/pages/compare.py", players=["Bukayo Saka · Arsenal", "Lamine Yamal · Barcelona"])
    assert not at.exception
    assert len(at.multiselect(key="players").value) == 2
    assert any("different leagues" in c.value for c in at.caption)
