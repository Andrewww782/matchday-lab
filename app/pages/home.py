import pandas as pd
import streamlit as st

from app import data, ui

PAGES = st.session_state["pages"]

if not data.available("upcoming"):
    ui.missing("This week's predictions")
    st.stop()

league = ui.league_picker()
name = data.league_name(league)
st.title(f"This week in the {name}" if league == "EPL" else f"This week in {name}")
st.markdown("Predictions, player values and scouting, all in plain English. Updated every week.")

up = data.table("upcoming")
up = up[up["league"] == league]
if up.empty:
    st.info(f"No upcoming {name} fixtures right now. The season may be on a break.")
    st.stop()
gw = int(up.sort_values("kickoff")["gw"].iloc[0])
round_name = "Gameweek" if league == "EPL" else "Matchday"
week = up[up["gw"] == gw].sort_values("kickoff")
st.html(ui.banner(name, f"{round_name} {gw} · {len(week)} games"))
st.subheader(f"{round_name} {gw} predictions")
now = pd.Timestamp.now(tz="UTC")
cols = st.columns(2)
for i, f in enumerate(week.itertuples()):
    with cols[i % 2], st.container(border=True, key=f"fmcard_fx{i}"):
        ko = pd.Timestamp(f.kickoff)
        when = ko.tz_convert("Europe/London").strftime("%a %d %b · %H:%M")
        soon = now <= ko <= now + pd.Timedelta(hours=48)
        st.html(ui.club_stripe(f.home, f.away)
                + (f'<div class="ml-muted"><span class="fm-live"></span><span class="fm-soon">Soon</span> · {when} UK</div>'
                   if soon else f'<div class="ml-muted">{when} UK</div>')
                + f'<div style="display:flex;justify-content:space-between;margin:.2rem 0">'
                f'{ui.badge(f.home)}<span class="ml-muted">vs</span>{ui.badge(f.away)}</div>'
                + ui.prob_bar(f.home, f.away, f.p_h, f.p_d, f.p_a)
                + (f'<div class="ml-muted" style="margin-top:.35rem">Likely score '
                   f'<b>{ui.parse_scores(f.top_scores)[0][0]}</b> · Over 2.5 goals {f.p_over25:.0%}</div>'
                   if isinstance(getattr(f, "top_scores", None), str) else ""))
        st.page_link(PAGES["match"], label="Why?", icon=":material/help:",
                     query_params={"home": f.home, "away": f.away})

st.divider()
left, right = st.columns([3, 2], gap="large")
with left:
    if league == "EPL" and data.available("fpl_players"):
        st.subheader("Players to watch this week")
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
    elif data.available("values", "players"):
        st.subheader(f"Bargains in {name}")
        st.caption("Players whose numbers say they're worth more than their market value.")
        v = data.table("values")
        v = v[(v["league"] == league) & (v["tm_value"] >= 3e6)].merge(
            data.table("players")[["pid", "name", "team", "age"]], on="pid")
        top = v.sort_values("value_ratio", ascending=False).head(8)
        st.dataframe(pd.DataFrame({
            "Player": top["name"], "Club": top["team"], "Age": top["age"].round(0),
            "Numbers say": top["est_value"].map(ui.money), "Market": top["tm_value"].map(ui.money)}),
            hide_index=True, width="stretch")
        st.page_link(PAGES["value"], label="More player values", icon=":material/arrow_forward:")
with right:
    st.subheader("Explore")
    for key, blurb in [("match", "Pick any two clubs and see who's favourite, and why."),
                       ("sim", "Title, Champions League and relegation odds, plus what-ifs."),
                       ("value", "Is he a bargain or overpriced, based on his numbers?"),
                       ("scout", "Find players with a similar style, anywhere in Europe."),
                       ("compare", "Put two or three players side by side.")]:
        st.page_link(PAGES[key], label=f"**{PAGES[key].title}**: {blurb}", icon=PAGES[key].icon)
