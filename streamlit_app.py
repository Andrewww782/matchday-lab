"""FootyMinds - top-5-league predictions, player values and scouting for fans."""
import streamlit as st

from app import ui

st.set_page_config(page_title="FootyMinds", page_icon="static/ball.png", layout="wide")
st.logo("static/logo.png", size="large")
ui.inject_css()
# Pages without a league picker keep the league touch of the league last picked.
ui.set_league_accent(st.session_state.get("league"))

PAGES = {
    "home": st.Page("app/pages/home.py", title="This week", icon=":material/home:", default=True),
    "match": st.Page("app/pages/match.py", title="Who wins?", icon=":material/sports_soccer:", url_path="match"),
    "value": st.Page("app/pages/value.py", title="What's he worth?", icon=":material/payments:", url_path="value"),
    "scout": st.Page("app/pages/scout.py", title="Who plays like him?", icon=":material/person_search:", url_path="scout"),
    "compare": st.Page("app/pages/compare.py", title="Head-to-head", icon=":material/compare_arrows:", url_path="compare"),
    "sim": st.Page("app/pages/simulator.py", title="Where will they finish?", icon=":material/leaderboard:", url_path="table"),
    "offside": st.Page("app/pages/offside.py", title="Offside check", icon=":material/straighten:", url_path="offside"),
    "var": st.Page("app/pages/var.py", title="Fan VAR", icon=":material/sports:", url_path="var"),
    "about": st.Page("app/pages/about.py", title="How it works", icon=":material/info:", url_path="about"),
    "find": st.Page("app/pages/find.py", title="Find a player", icon=":material/search:", url_path="find"),
}
st.session_state["pages"] = PAGES

# Top bar. Single pages sit in the "" section; the stylesheet orders the bar as
# This week · [Fan VAR] · Matches ▾ · Players ▾ · How it works · [Find a player].
# Fantasy (app/pages/fpl.py) is parked for a later update: its data still builds, it's just not in the menu.
nav = st.navigation({
    "": [PAGES["home"], PAGES["var"], PAGES["about"], PAGES["find"]],
    "Matches": [PAGES["match"], PAGES["sim"], PAGES["offside"]],
    "Players": [PAGES["value"], PAGES["scout"], PAGES["compare"]],
}, position="top")

try:
    nav.run()
finally:  # pages end early with st.stop(); the footer still belongs at the bottom
    ui.footer()
