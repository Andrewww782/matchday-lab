import html

import pandas as pd
import streamlit as st

from app import data, ui, var_ui, votes

PAGES = st.session_state["pages"]

if not data.available("upcoming"):
    ui.missing("This week's predictions")
    st.stop()

league = ui.league_picker()
name = data.league_name(league)
the_name = f"the {name}" if league == "EPL" else name
up = data.table("upcoming")
up = up[up["league"] == league]
round_name = "Gameweek" if league == "EPL" else "Matchday"
gw = int(up.sort_values("kickoff")["gw"].iloc[0]) if len(up) else None
week = up[up["gw"] == gw].sort_values("kickoff") if gw else up

# ---- Fan VAR: the headline act ----
hot = pd.DataFrame()
if data.available("incidents", "var_matches"):
    inc = data.table("incidents")
    inc = inc[(inc.league == league) & inc.big]
    last = inc.gw.max() if len(inc) else None
    hot = inc[inc.gw == last].copy()
    if len(hot):
        s = votes.summary(hot.incident_id)
        hot = hot.join(s, on="incident_id")
        # the calls fans are arguing about most, then the newest
        hot["heat"] = hot["n"].fillna(0) * (1 - (hot["wrong_pct"].fillna(0.5) - 0.5).abs())
        drama = {"goal_overturned": 6, "var_penalty": 5, "var_red": 5, "red": 4, "penalty": 3, "var_no_penalty": 2}
        hot["drama"] = hot["kind"].map(drama).fillna(1)
        hot = hot.sort_values(["heat", "drama", "kickoff"], ascending=False).head(3)
ui.hero("You're the <em>VAR</em>",
        f"Every big refereeing call in {the_name}. Watch it, judge it, see if other fans agree. "
        "Plus match predictions and player values.",
        tag=f"{round_name} {int(last)} · {len(inc[inc.gw == last])} big calls" if len(hot) else "")
if len(hot):
    ui.eyebrow("Your call")
    st.subheader("Hottest calls right now")
    cols = st.columns(len(hot))
    for c, r in zip(cols, hot.to_dict("records")):
        with c:
            var_ui.card(r, compact=True, scope="home")
    st.page_link(PAGES["var"], label="See every call and give your verdict", icon=":material/sports:")

# ---- This week's predictions ----
if up.empty:
    st.info(f"No upcoming {name} fixtures right now. The season may be on a break.")
    st.stop()
st.divider()
ui.eyebrow("This week's games")
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
    if data.available("values", "players"):
        ui.eyebrow("Transfer watch")
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
    if data.available("players"):
        st.markdown("")
        ui.player_search(key="home_find")
with right, st.container(key="fmexplore"):
    st.subheader("Explore")
    for key, blurb in [("var", "Judge every big refereeing call. Were the refs right?"),
                       ("match", "Pick any two clubs and see who's favourite, and why."),
                       ("sim", "Title, Champions League and relegation odds, plus what-ifs."),
                       ("value", "Is he a bargain or overpriced, based on his numbers?"),
                       ("scout", "Find players with a similar style, anywhere in Europe."),
                       ("compare", "Put two or three players side by side.")]:
        st.page_link(PAGES[key], label=f"**{PAGES[key].title}**: {blurb}", icon=PAGES[key].icon)
