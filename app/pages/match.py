import numpy as np
import pandas as pd
import streamlit as st

from app import data, theme, ui

st.title("Who wins?")
st.markdown("Pick two clubs to see each side's chances, and what's driving the prediction.")

if not data.available("pair_probs", "upcoming"):
    ui.missing("Match predictions")
    st.stop()

league = ui.league_picker()
pairs = data.table("pair_probs").query("league == @league")
up = data.table("upcoming").query("league == @league")
nxt = up.sort_values("kickoff").iloc[0] if len(up) else pairs.iloc[0]
NOT_FACTORS = {"league", "home", "away", "p_h", "p_d", "p_a", "fixture_id", "gw", "kickoff",
               "xg_h", "xg_a", "p_btts", "p_over25", "p_cs_h", "p_cs_a", "top_scores", "grid"}
GROUPS = [c for c in pairs.columns if c not in NOT_FACTORS]
round_name = "Gameweek" if league == "EPL" else "Matchday"

c1, c2 = st.columns(2)
with c1:
    home = ui.team_picker("Home team", "home", nxt["home"], league)
with c2:
    away = ui.team_picker("Away team", "away", nxt["away"], league)

if home == away:
    st.warning("Pick two different clubs.")
    st.stop()

fixture = up[(up.home == home) & (up.away == away)]
row = fixture.iloc[0] if len(fixture) else pairs[(pairs.home == home) & (pairs.away == away)].iloc[0]

if len(fixture):
    when = pd.Timestamp(row["kickoff"]).tz_convert("Europe/London").strftime("%A %d %B, %H:%M")
    st.html(ui.banner(data.league_name(league), f"{round_name} {int(row['gw'])} · {when} UK"))
else:
    st.html(ui.banner(data.league_name(league), "Any two clubs"))
    st.caption("Not a scheduled fixture yet, so this assumes a normal week's rest for both teams.")

p = {"H": row["p_h"], "D": row["p_d"], "A": row["p_a"]}
pick = max(p, key=p.get)
headline = {"H": f"{home} win", "D": "a draw", "A": f"{away} win"}[pick]
confidence = "Too close to call" if max(p.values()) < 0.4 else \
    "Slight favourite" if max(p.values()) < 0.5 else "Favourite" if max(p.values()) < 0.65 else "Strong favourite"

with st.container(border=True, key="fmcard_match"):
    st.html(ui.club_stripe(home, away)
            + f'<div style="display:flex;justify-content:space-between;font-size:1.2rem;margin-bottom:.2rem">'
            f'{ui.badge(home)}<span class="ml-muted">vs</span>{ui.badge(away)}</div>'
            + ui.prob_bar(home, away, row["p_h"], row["p_d"], row["p_a"], big=True))
    st.markdown(f"**Most likely: {headline} ({p[pick]:.0%})** · {confidence}")

if "top_scores" in row and pd.notna(row.get("top_scores")):
    st.subheader("The score")
    scores = ui.parse_scores(row["top_scores"])
    best, best_p = scores[0]
    st.markdown(f"Expected goals: **{home} {row['xg_h']:.1f} – {row['xg_a']:.1f} {away}**. "
                f"Most likely score **{best}** ({best_p:.0%}), but football is random: no single score is "
                "likely, so here are the top five.")
    st.html(ui.score_chips(row["top_scores"]))
    h_goals, a_goals = (int(x) for x in best.split("–"))
    best_is_draw = h_goals == a_goals
    if best_is_draw and pick != "D":
        st.caption(f"Why a draw, if {headline} is more likely? A win can happen many ways (1–0, 2–0, 2–1…), "
                   f"so each of those scores is less likely on its own than {best}, even though together "
                   "they add up to more.")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Both teams score", f"{row['p_btts']:.0%}")
    m2.metric("Over 2.5 goals", f"{row['p_over25']:.0%}", help="3 or more goals in the game.")
    m3.metric(f"{home} clean sheet", f"{row['p_cs_h']:.0%}")
    m4.metric(f"{away} clean sheet", f"{row['p_cs_a']:.0%}")
    with st.expander("All scorelines"):
        import plotly.express as px
        n = int(round(len(row["grid"]) ** 0.5))
        g = np.array(row["grid"]).reshape(n, n)[:6, :6] * 100
        fig = px.imshow(g, x=[str(i) for i in range(6)], y=[str(i) for i in range(6)], text_auto=".0f",
                        color_continuous_scale=theme.league_scale(league), labels=dict(x=f"{away} goals", y=f"{home} goals"))
        fig.update_traces(hovertemplate=f"{home} %{{y}} – %{{x}} {away}: %{{z:.1f}}%<extra></extra>")
        fig.update_layout(height=380, margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False)
        st.plotly_chart(fig, width="stretch")
        st.caption("Chance of each exact score, in %. Scores above 5 goals are left out (they're rare).")

st.subheader("Why?")
items = sorted([(g, float(row[g])) for g in GROUPS if abs(row[g]) >= 0.5], key=lambda x: -abs(x[1]))
if not items:
    st.markdown("These two sides look evenly matched on every measure.")
else:
    def edge(team, sign):
        gs = [g.lower() for g, v in items[:4] if (v > 0) == (sign > 0) and abs(v) >= 2]
        return f"**{team}** have the edge on {' and '.join(gs)}" if gs else None

    parts = [p for p in (edge(home, 1), edge(away, -1)) if p]
    st.markdown(("; ".join(parts) + ".") if parts else "Nothing stands out much either way.")
    st.html(ui.why_bars(items, f"Helps {away}", f"Helps {home}", unit=" pts"))
    st.caption("Each bar shows how many percentage points that factor adds to one side's edge "
               "(chance of winning minus the opponent's). Home advantage is built in on top.")

ui.how_it_works("""
We compare the two clubs on:
- **Overall team strength**: a rating that goes up when you win and down when you lose,
  more so against strong opponents (an *Elo* rating, like in chess).
- **Recent form** over the last 5 and 10 league games: chances created and conceded (expected
  goals, *xG*), goals, shots and points.
- **Rest**: days since each side's last league game.
- **Attack & defence strength**: a goals model that learns how many goals each club tends to
  score and concede (from real goals and expected goals, recent games counting more).

The final chances are an average of two models trained on every game in Europe's top five leagues
since 2016 (about 18,000): a form model and the goals model. Together they beat either one alone.
The goals model also gives the scorelines. Both only learn from games before the ones they predict,
so this season's predictions are a genuine test.
""")

st.divider()
st.subheader("How has it done this season?")
if not data.available("track_record"):
    st.caption("No finished matches yet this season.")
    st.stop()

tr = data.table("track_record").query("league == @league").sort_values("date", ascending=False)
if tr.empty:
    st.caption("No finished matches yet this season.")
    st.stop()
m = data.meta("match_metrics")
acc = (tr["pick"] == tr["result"]).mean()
bacc = (tr["bookie_pick"] == tr["result"])[tr["bookie_pick"].notna()].mean()
k1, k2, k3 = st.columns(3)
k1.metric("Results called correctly", f"{acc:.0%}", help="The most likely outcome was what happened.")
k2.metric("Bookmakers (same games)", f"{bacc:.0%}")
k3.metric("Games so far", len(tr))
if "top3_hit" in tr:
    over = (tr["home_goals"] + tr["away_goals"]) >= 3
    ok = tr["bookie_over25"].notna()
    k4, k5, k6 = st.columns(3)
    k4.metric("Exact score in our top 3", f"{tr['top3_hit'].mean():.0%}",
              help="Exact scores are hard: about 30% is good.")
    k5.metric("Over/under 2.5 called", f"{((tr['p_over25'] > 0.5) == over).mean():.0%}")
    k6.metric("Bookmakers, over/under", f"{((tr.loc[ok, 'bookie_over25'] > 0.5) == over[ok]).mean():.0%}")
v = m.get("headline", m).get("by_league", {}).get(league)
if v:
    st.caption(f"Last season as a test: in the {data.league_name(league)} our model called "
               f"{v['model']['accuracy']:.0%} of results correctly vs {v['bookmaker']['accuracy']:.0%} "
               "for the bookmakers. Football is hard to predict: about half is typical.")

show = tr.head(20).copy()
names = {"H": "Home", "D": "Draw", "A": "Away"}
show["Match"] = show["home"] + " " + show["home_goals"].astype(str) + "–" + show["away_goals"].astype(str) + " " + show["away"]
show["We said"] = show["pick"].map(names) + " (" + (show[["p_h", "p_d", "p_a"]].max(axis=1) * 100).round().astype(int).astype(str) + "%)"
show["Right?"] = np.where(show["pick"] == show["result"], "✅", "❌")
show["Date"] = pd.to_datetime(show["date"]).dt.strftime("%d %b")
cols = ["Date", "Match", "We said", "Right?"]
if "likely_score" in show:
    show["Likely score"] = show["likely_score"].str.replace("-", "–")
    cols.insert(3, "Likely score")
st.dataframe(show[cols], hide_index=True, width="stretch")
