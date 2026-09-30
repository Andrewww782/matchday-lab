import pandas as pd
import streamlit as st

from app import data, ui, var_ui, votes

if not data.available("incidents", "var_matches"):
    ui.missing("Fan VAR")
    st.stop()

league = ui.league_picker()
name = data.league_name(league)
inc_all = data.table("incidents")
matches_all = data.table("var_matches")
inc = inc_all[inc_all.league == league]
matches = matches_all[matches_all.league == league].sort_values("kickoff", ascending=False)
round_name = "Gameweek" if league == "EPL" else "Matchday"

rounds = sorted(matches.gw.dropna().unique().tolist(), reverse=True)
latest = rounds[0] if rounds else None
big_latest = int(inc[(inc.gw == latest) & inc.big].shape[0]) if latest else 0
ui.hero("You're the <em>VAR</em>",
        f"Every big refereeing call in {name if league != 'EPL' else 'the Premier League'}: watch it, "
        "judge it, and see whether other fans agree.",
        tag=f"{round_name} {latest} · {big_latest} big calls" if latest else "")

teams = data.teams(None)
c1, c2 = st.columns([1, 1])
with c1:
    rnd = st.selectbox(round_name, rounds, format_func=lambda g: f"{round_name} {g}", key=f"var_round_{league}")
with c2:
    current = votes.supports()
    club = st.selectbox("Who do you support? (optional)", ["No one / neutral"] + teams,
                        index=(teams.index(current) + 1) if current in teams else 0,
                        help="So we can compare what each club's fans think with what neutrals think. "
                             "It stays on this device.")
    picked = None if club == "No one / neutral" else club
    if picked != current:
        votes.set_supports(picked)

big, every, verdicts = st.tabs(["Big calls", "Every match", "Verdicts"])

with big:
    calls = inc[(inc.gw == rnd) & inc.big].copy()
    calls = pd.concat([calls, pd.DataFrame(var_ui.flag_rows(matches[matches.gw == rnd]))], ignore_index=True)
    if calls.empty:
        st.info(f"No big calls in {round_name} {rnd}: the refs had a quiet week. Check another {round_name.lower()}.")
    else:
        order = st.segmented_control("Sort", ["Newest", "Most controversial", "Most 'wrong'"], default="Newest",
                                     required=True, key="var_sort", label_visibility="collapsed")
        s = votes.summary(calls.incident_id)
        calls = calls.join(s, on="incident_id")
        if order == "Most controversial":
            calls = calls.assign(k=1 - (calls.wrong_pct.fillna(0.5) - 0.5).abs()).sort_values(["k", "n"], ascending=False)
        elif order == "Most 'wrong'":
            calls = calls.sort_values(["wrong_pct", "n"], ascending=False, na_position="last")
        else:
            calls = calls.sort_values(["kickoff", "seconds"], ascending=[False, True])
        st.caption(f"{len(calls)} calls from {round_name} {rnd}. Vote on as many as you like; you can change your mind.")
        cols = st.columns(2)
        for i, r in enumerate(calls.to_dict("records")):
            with cols[i % 2]:
                var_ui.card(r, scope="big")

with every:
    labels = {r.event_id: f"{pd.Timestamp(r.kickoff).strftime('%d %b')} · {r.home} {r.score} {r.away}"
              for r in matches.itertuples()}
    ev = st.selectbox("Match", list(labels), format_func=labels.get, key=f"var_match_{league}")
    if ev:
        m = matches[matches.event_id == ev].iloc[0]
        if m.referee:
            st.caption(f"Referee: {m.referee}")
        mine = inc[inc.event_id == ev].sort_values("seconds")
        mine = pd.concat([mine, pd.DataFrame(var_ui.flag_rows(matches[matches.event_id == ev]))], ignore_index=True)
        if mine.empty:
            st.info("No cards, penalties or VAR checks in this one. A clean game!")
        cols = st.columns(2)
        for i, r in enumerate(mine.to_dict("records")):
            with cols[i % 2]:
                var_ui.card(r, compact=r["kind"] == "yellow", scope="every")
        var_ui.flag_form(m)

with verdicts:
    season = inc[inc.big]
    summ = votes.summary(season.incident_id)
    st.caption(f"The whole {name} season so far. Tables fill up as fans vote.")
    ui.eyebrow("Hot takes")
    st.subheader("Most controversial calls")
    con = var_ui.controversy(summ, season)
    if con.empty:
        st.info("Not enough votes yet. Be one of the first: pick a call in *Big calls* and give your verdict.")
    else:
        top = con.sort_values(["split", "n"], ascending=False).head(10)
        st.dataframe(pd.DataFrame({
            "Call": top.headline, "Match": top.home + " v " + top.away, "Minute": top.minute,
            "Fans saying wrong": top.wrong_pct * 100, "Votes": top.n.astype(int)}),
            hide_index=True, width="stretch",
            column_config={"Fans saying wrong": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)})
    c1, c2 = st.columns(2, gap="large")
    with c1:
        ui.eyebrow("Referees")
        st.subheader("Referee report card")
        rt = var_ui.referee_table(summ, season)
        if rt.empty:
            st.caption("Referees appear once they have 3 calls with at least 5 votes each.")
        else:
            st.dataframe(pd.DataFrame({"Referee": rt.index, "Fans agree": rt.agree * 100, "Calls": rt.calls}),
                         hide_index=True, width="stretch",
                         column_config={"Fans agree": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)})
    with c2:
        ui.eyebrow("Hard done by")
        st.subheader("Who gets robbed?")
        rb = var_ui.robbed_table(summ, season)
        if rb.empty:
            st.caption("Clubs appear once calls against them have at least 5 votes.")
        else:
            st.dataframe(rb.reset_index(names="Club"), hide_index=True, width="stretch")

ui.how_it_works("""
- **Where the calls come from:** every finished match's live commentary (via ESPN) is scanned for the
  moments refs get argued about: penalties, red cards, VAR checks and goals ruled out. Yellow cards are
  in *Every match*.
- **Voting:** one vote per call per device, no sign-up. You can change your vote any time.
- **"Fans are split"** means close to 50/50; "howler" means at least 75% say the ref got it wrong.
- **Fan flags:** if the ref missed something (a penalty, a red card), flag it in *Every match*. When three
  fans flag the same moment, it becomes a call everyone can vote on.
- **Highlights** are official league videos on YouTube. Not every incident makes the highlights.
""")
