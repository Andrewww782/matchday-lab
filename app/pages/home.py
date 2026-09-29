import pandas as pd
import streamlit as st

from app import data, ui

PAGES = st.session_state["pages"]

st.title("This week in the Premier League")
st.markdown("Predictions, player values and scouting, all in plain English. Updated every week.")

if not data.available("upcoming"):
    ui.missing("This week's predictions")
    st.stop()

up = data.table("upcoming")
gw = int(up["gw"].min())
week = up[up["gw"] == gw].sort_values("kickoff")

st.subheader(f"Gameweek {gw} predictions")
cols = st.columns(2)
for i, f in enumerate(week.itertuples()):
    with cols[i % 2], st.container(border=True):
        when = pd.Timestamp(f.kickoff).tz_convert("Europe/London").strftime("%a %d %b · %H:%M")
        st.html(f'<div class="ml-muted">{when}</div>'
                f'<div style="display:flex;justify-content:space-between;margin:.2rem 0">'
                f'{ui.badge(f.home)}<span class="ml-muted">vs</span>{ui.badge(f.away)}</div>'
                + ui.prob_bar(f.home, f.away, f.p_h, f.p_d, f.p_a))
        st.page_link(PAGES["match"], label="Why?", icon=":material/help:",
                     query_params={"home": f.home, "away": f.away})

st.divider()
left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("Players to watch this week")
    if data.available("fpl_players"):
        fp = data.table("fpl_players")
        top = fp.sort_values("xpts_next", ascending=False).head(8)
        st.dataframe(
            top[["web_name", "team", "pos", "xpts_next", "form"]].rename(columns={
                "web_name": "Player", "team": "Club", "pos": "Pos",
                "xpts_next": "Expected FPL pts", "form": "Form"}),
            hide_index=True, width="stretch",
            column_config={"Expected FPL pts": st.column_config.ProgressColumn(
                format="%.1f", min_value=0, max_value=float(top["xpts_next"].max()))})
        st.page_link(PAGES["fpl"], label="More fantasy picks", icon=":material/arrow_forward:")
with right:
    st.subheader("Explore")
    for key, blurb in [("match", "Pick any two clubs and see who's favourite, and why."),
                       ("sim", "Title, top-4 and relegation odds, plus what-ifs."),
                       ("value", "Is he a bargain or overpriced, based on his numbers?"),
                       ("scout", "Find players with a similar style."),
                       ("compare", "Put two or three players side by side.")]:
        st.page_link(PAGES[key], label=f"**{PAGES[key].title}** — {blurb}", icon=PAGES[key].icon)
