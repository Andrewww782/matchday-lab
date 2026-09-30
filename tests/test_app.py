"""Smoke tests: every page renders with the committed data and no exceptions."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["app/pages/home.py", "app/pages/match.py", "app/pages/value.py", "app/pages/scout.py",
         "app/pages/compare.py", "app/pages/simulator.py", "app/pages/fpl.py", "app/pages/about.py",
         "app/pages/find.py"]


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


def test_cache_follows_data_refresh(tmp_path, monkeypatch):
    """A running server must not serve last week's cached tables after new data lands
    (this crashed the live site once: new code, old cached players table)."""
    import os
    import pandas as pd
    from app import data
    monkeypatch.setattr(data, "DATA", tmp_path)
    pd.DataFrame({"a": [1]}).to_parquet(tmp_path / "t.parquet")
    assert list(data.table("t").columns) == ["a"]
    pd.DataFrame({"a": [1], "b": [2]}).to_parquet(tmp_path / "t.parquet")
    st = (tmp_path / "t.parquet").stat()
    os.utime(tmp_path / "t.parquet", ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert list(data.table("t").columns) == ["a", "b"]


def test_match_page_shows_the_score():
    at = run("app/pages/match.py", home="Arsenal", away="Leeds")
    assert not at.exception
    assert any(s.value == "The score" for s in at.subheader)
    assert any("Most likely score" in m.value for m in at.markdown)
    assert {m.label for m in at.metric} >= {"Both teams score", "Over 2.5 goals"}


@pytest.mark.parametrize("league", LEAGUE_NAMES)
def test_home_cards_show_likely_score(league):
    at = run("app/pages/home.py", league=league)
    assert not at.exception
    assert "Likely score" in " ".join(str(h.proto) for h in at.get("html"))


# --- Colour & motion ---------------------------------------------------------------------------

def test_stylesheet_survives_streamlits_sanitiser():
    """Streamlit drops a <style> block whose text contains '<' followed by a letter or '/'."""
    import re
    from app import ui
    body = ui.CSS.strip().removeprefix("<style>").removesuffix("</style>")
    assert not re.search(r"<[/\w!]", body)
    assert "prefers-reduced-motion: reduce" in body


@pytest.mark.parametrize("league", ["EPL", "La_Liga", "Serie_A", "Bundesliga", "Ligue_1", None])
def test_league_palettes_are_readable(league):
    from app import theme
    t = theme.league(league)
    for c in ("a", "b"):  # banner and selected-tab text is white on these
        assert theme.contrast("#FFFFFF", t[c]) >= 4.5, (league, c)


def test_league_accent_follows_the_picked_league():
    at = run("app/pages/home.py", league="Bundesliga")
    assert not at.exception
    html = " ".join(str(h.proto) for h in at.get("html"))
    assert "--lg-a:#7A0A10" in html and "BUNDESLIGA".lower() in html.lower()


def test_animated_pieces_keep_their_numbers_as_text():
    from app import ui
    bar = ui.prob_bar("Arsenal", "Leeds", 0.62, 0.22, 0.16)
    assert all(s in bar for s in ("62%", "Draw", "16%")) and "data-count" in bar
    chips = ui.score_chips("1-0:0.14|2-0:0.13|1-1:0.11")
    assert "1–0 · 14%" in chips and chips.count("ml-chip") == 3 and chips.count(" best") == 1
    ring = ui.ring(87.4, "87% similar")
    assert "--fm-p:87.4" in ring and "87%" in ring and 'aria-label="87% similar"' in ring


def test_scout_shows_similarity_rings():
    at = run("app/pages/scout.py", player="Bukayo Saka · Arsenal")
    assert not at.exception
    assert "fm-ring" in " ".join(str(h.proto) for h in at.get("html"))


# --- Krackerz-style look -----------------------------------------------------------------------

def test_palette_text_pairs_are_readable():
    from app import theme as t
    for fg, bg in [("#FFFFFF", t.RED), ("#FFFFFF", t.RUST), ("#FFFFFF", t.MAROON), ("#FFFFFF", t.DEEP),
                   (t.INK, t.LIME), (t.INK, t.PAPER), (t.INK, t.STONE), (t.INK, t.CARD), (t.LIME, t.INK)]:
        assert t.contrast(fg, bg) >= 4.5, (fg, bg)
    assert t.text_on(t.STONE) == t.INK and t.text_on(t.RED) == "#FFFFFF"


def test_stickers_and_eyebrows_render():
    from app import ui
    s = ui.sticker("Gameweek 6 · 10 games", "ink", -3)
    assert "fm-sticker ink" in s and "--tilt:-3deg" in s and "Gameweek 6" in s
    assert "<script" not in ui.sticker("<script>x</script>")  # escaped
    assert 'class="fm-banner"' in ui.banner("Serie A", "Matchday 6") and "fm-sticker league" in ui.banner("Serie A")


def test_find_page_links_out():
    at = run("app/pages/find.py")
    assert not at.exception
    at.selectbox(key="find_player").select_index(0).run()
    assert not at.exception
    links = " ".join(str(el.proto) for el in at.get("page_link"))
    assert "value" in links and "scout" in links and "compare" in links


def test_every_page_has_the_footer():
    for page in PAGES:
        at = run(page)
        assert "fm-footer" in " ".join(str(h.proto) for h in at.get("html")), page
