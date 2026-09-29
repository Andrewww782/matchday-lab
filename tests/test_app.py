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
    fid = int(pd.read_parquet(ROOT / "data" / "upcoming.parquet")["fixture_id"].iloc[0])
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    at.run()
    at.session_state["whatif"] = {fid: "A"}
    at.switch_page("app/pages/simulator.py").run()
    assert not at.exception
    assert any("locked in" in c.value for c in at.caption)
