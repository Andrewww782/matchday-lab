import pandas as pd
import streamlit as st

from app import data, ui, var_ui, votes

PAGES = st.session_state["pages"]

st.title("Club *profile*")
st.markdown("Pick any club in Europe's top five leagues: recent form, what's next, who to watch, "
            "and how Fan VAR calls have gone for them.")

if not data.available("fixtures", "teams"):
    ui.missing("Club data")
    st.stop()

league = ui.league_picker()
up_all = data.table("upcoming").query("league == @league") if data.available("upcoming") else pd.DataFrame()
default = (up_all.sort_values("kickoff")["home"].iloc[0] if len(up_all) else data.teams(league)[0])
team = ui.team_picker("Club", "team", default, league)

with st.container(border=True, key="fmcard_team"):
    st.html(ui.club_stripe(team)
            + f'<div style="font-size:1.3rem;font-weight:700">{team}</div>'
            f'<div class="ml-muted">{ui.badge(team)} · {data.league_name(league)}</div>')

# ---- Recent form ----
ui.eyebrow("Form")
st.subheader("How have they been playing?")
fx = data.table("fixtures").query("league == @league and finished and (home == @team or away == @team)")
recent = fx.sort_values("kickoff", ascending=False).head(5).sort_values("kickoff")
if recent.empty:
    st.caption("No finished matches yet this season.")
else:
    def result(r):
        us, them = (r.home_goals, r.away_goals) if r.home == team else (r.away_goals, r.home_goals)
        return "W" if us > them else "L" if us < them else "D"

    st.html(ui.form_pills([result(r) for r in recent.itertuples()]))
    st.caption("Last " + str(len(recent)) + " league games, oldest to newest.")

if data.available("team_state"):
    ts = data.table("team_state")
    row = ts[(ts.league == league) & (ts.team == team)]
    if len(row) and pd.notna(row["pts_5"].iloc[0]):
        r = row.iloc[0]
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Elo rating", f"{r['elo']:.0f}")
        k2.metric("Points per game (L5)", f"{r['pts_5']:.1f}")
        k3.metric("xG for (L5)", f"{r['xgf_5']:.1f}")
        k4.metric("xG against (L5)", f"{r['xga_5']:.1f}")

# ---- Upcoming fixtures with predicted scorelines ----
st.divider()
ui.eyebrow("Fixtures")
st.subheader("What's next?")
if not data.available("upcoming"):
    ui.missing("Fixture predictions")
else:
    up = up_all[(up_all.home == team) | (up_all.away == team)].sort_values("kickoff").head(5)
    if up.empty:
        st.info(f"No upcoming {data.league_name(league)} fixtures for {team} right now. "
                "The season may be on a break, or their fixtures aren't out yet.")
    else:
        for i, f in enumerate(up.itertuples()):
            with st.container(border=True, key=f"fmcard_teamfx{i}"):
                when = pd.Timestamp(f.kickoff).tz_convert("Europe/London").strftime("%a %d %b · %H:%M")
                st.html(ui.club_stripe(f.home, f.away)
                        + f'<div class="ml-muted">{when} UK</div>'
                        + f'<div style="display:flex;justify-content:space-between;margin:.2rem 0">'
                        f'{ui.badge(f.home)}<span class="ml-muted">vs</span>{ui.badge(f.away)}</div>'
                        + ui.prob_bar(f.home, f.away, f.p_h, f.p_d, f.p_a)
                        + (f'<div class="ml-muted" style="margin-top:.35rem">Likely score '
                           f'<b>{ui.parse_scores(f.top_scores)[0][0]}</b> · Over 2.5 goals {f.p_over25:.0%}</div>'
                           if isinstance(getattr(f, "top_scores", None), str) else ""))
                st.page_link(PAGES["match"], label="Why?", icon=":material/help:",
                             query_params={"home": f.home, "away": f.away})

# ---- Top players ----
st.divider()
ui.eyebrow("Squad")
st.subheader("Who to watch")
if not data.available("players"):
    ui.missing("Player data")
else:
    squad = data.table("players").query("team == @team").copy()
    if squad.empty:
        st.caption("No player data for this club yet.")
    else:
        squad["involvement"] = squad["win_npg"].fillna(0) + squad["win_xA"].fillna(0)
        top = squad.sort_values("involvement", ascending=False).head(5)
        for r in top.itertuples():
            with st.container(border=True, key=f"fmcard_squad{r.pid}"):
                a, b = st.columns([5, 2], vertical_alignment="center")
                age = f"age {r.age:.0f} · " if pd.notna(r.age) else ""
                a.html(f'<b>{r.name}</b><br><span class="ml-muted">{r.pos} · {age}{ui.money(r.tm_value)}</span>')
                b.page_link(PAGES["player"], label="Profile", icon=":material/badge:",
                           query_params={"player": data.player_label(r.pid)})

# ---- Fan VAR verdicts ----
st.divider()
ui.eyebrow("Fan VAR")
st.subheader("Did the refs get it right?")
if not data.available("incidents", "var_matches"):
    ui.missing("Fan VAR")
else:
    inc = data.table("incidents")
    inc = inc[(inc.home == team) | (inc.away == team)]
    if inc.empty:
        st.caption(f"No big calls involving {team} yet this season.")
    else:
        summ = votes.summary(inc.incident_id)
        against, favour = var_ui.team_record(summ, inc, team)
        c1, c2 = st.columns(2)
        c1.metric("Wrong calls against them", against)
        c2.metric("Wrong calls in their favour", favour)
        recent_inc = inc.sort_values("kickoff", ascending=False).head(3)
        for r in recent_inc.to_dict("records"):
            var_ui.card(r, compact=True, scope="team")
        st.page_link(PAGES["var"], label="See every call", icon=":material/sports:")

ui.how_it_works("""
**Form** comes from an Elo rating (goes up when you win, more so against strong opponents) plus
rolling averages over the last 5 and 10 league games.

**Fixtures** blend a form model and a Dixon-Coles goals model, same as "Who wins?".

**Squad** is ranked by non-penalty goals plus expected assists over the last season and this one, a
measure that's available for players in every one of the top 5 leagues.

**Fan VAR** counts calls where most voting fans disagreed with the decision, split by whether it went
against this club or in their favour.
""")
