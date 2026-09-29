"""FootyMinds - Premier League predictions, player values and scouting for fans."""
import pandas as pd
import streamlit as st

from app import data, ui

st.set_page_config(page_title="FootyMinds", page_icon="⚽", layout="wide")
ui.inject_css()

PAGES = {
    "home": st.Page("app/pages/home.py", title="This week", icon=":material/home:", default=True),
    "match": st.Page("app/pages/match.py", title="Who wins?", icon=":material/sports_soccer:", url_path="match"),
    "value": st.Page("app/pages/value.py", title="What's he worth?", icon=":material/payments:", url_path="value"),
    "scout": st.Page("app/pages/scout.py", title="Who plays like him?", icon=":material/person_search:", url_path="scout"),
    "compare": st.Page("app/pages/compare.py", title="Head-to-head", icon=":material/compare_arrows:", url_path="compare"),
    "sim": st.Page("app/pages/simulator.py", title="Where will they finish?", icon=":material/leaderboard:", url_path="table"),
    "fpl": st.Page("app/pages/fpl.py", title="Fantasy picks", icon=":material/stars:", url_path="fantasy"),
    "about": st.Page("app/pages/about.py", title="How it works", icon=":material/info:", url_path="about"),
}
st.session_state["pages"] = PAGES

nav = st.navigation({
    "": [PAGES["home"]],
    "Matches": [PAGES["match"], PAGES["sim"]],
    "Players": [PAGES["value"], PAGES["scout"], PAGES["compare"]],
    "Fantasy": [PAGES["fpl"]],
    "More": [PAGES["about"]],
})

with st.sidebar:
    st.markdown("### ⚽ FootyMinds")
    if data.available("players"):
        idx = data.player_index()
        labels = idx.set_index("pid")["label"].to_dict()
        found = st.selectbox("Find a player", idx["pid"].tolist(), index=None,
                             format_func=lambda c: labels[c], placeholder="Any player in Europe's top 5…",
                             key="sidebar_find")
        if found is not None:
            q = {"player": labels[found]}  # bound widgets read their label from the URL
            st.page_link(PAGES["value"], label="What's he worth?", icon=":material/payments:", query_params=q)
            st.page_link(PAGES["scout"], label="Similar players", icon=":material/person_search:", query_params=q)
            st.page_link(PAGES["compare"], label="Compare him", icon=":material/compare_arrows:",
                         query_params={"players": labels[found]})
    m = data.meta("meta")
    if m:
        when = pd.Timestamp(m["updated_at"]).strftime("%d %b %Y")
        st.caption(f"{m['season']} · Premier League, La Liga, Serie A, Bundesliga, Ligue 1 · updated {when}")
    st.caption("Not affiliated with any league, club or FPL. Just for fun, not betting advice.")

nav.run()
