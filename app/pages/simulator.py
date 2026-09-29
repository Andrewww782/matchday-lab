import pandas as pd
import plotly.express as px
import streamlit as st

from app import data, ui
from app.simulate import current_table, simulate

st.title("Where will they finish?")
st.markdown("We play out the rest of the season **10,000 times** using the match predictions, then count "
            "how often each club finishes where. You can lock in results to see what changes.")

if not data.available("fixtures", "upcoming"):
    ui.missing("The season simulator")
    st.stop()

league = ui.league_picker()
rules = data.leagues()[league]
round_name = "Gameweek" if league == "EPL" else "Matchday"
fx = data.table("fixtures").query("league == @league")
table = current_table(fx, data.teams(league))
remaining = data.table("upcoming").query("league == @league").set_index("fixture_id")

# What-ifs are kept per league, so switching leagues doesn't mix them up.
locked: dict = st.session_state.setdefault("whatif", {}).setdefault(league, {})

with st.expander("What if…? Lock in some results", expanded=bool(locked)):
    gws = sorted(remaining["gw"].unique())
    gw = st.selectbox(round_name, gws, format_func=lambda g: f"{round_name} {g}", key=f"sim_gw_{league}")
    view = remaining[remaining["gw"] == gw].sort_values("kickoff")
    RES = {"Model decides": None, "Home win": "H", "Draw": "D", "Away win": "A"}
    INV = {v: k for k, v in RES.items()}
    ed = pd.DataFrame({"Home": view["home"], "Away": view["away"],
                       "Result": [INV[locked.get(i)] for i in view.index]}, index=view.index)
    out = st.data_editor(ed, hide_index=True, width="stretch", key=f"sim_edit_{league}_{gw}",
                         disabled=["Home", "Away"],
                         column_config={"Result": st.column_config.SelectboxColumn(options=list(RES), required=True)})
    for fid, res in out["Result"].items():
        if RES[res] is None:
            locked.pop(fid, None)
        else:
            locked[fid] = RES[res]
    if locked:
        c1, c2 = st.columns([3, 1], vertical_alignment="center")
        c1.caption(f"{len(locked)} result(s) locked in.")
        if c2.button("Clear all", width="stretch"):
            locked.clear()
            st.rerun()


@st.cache_data(ttl=3600, max_entries=128)
def run(league: str, locked_items: tuple, v: int) -> dict:  # v: data version, so refreshes aren't cached over
    fx = data.table("fixtures").query("league == @league")
    table = current_table(fx, data.teams(league))
    rem = data.table("upcoming").query("league == @league").set_index("fixture_id")
    r = data.leagues()[league]
    return simulate(table, rem, locked=dict(locked_items), cl=r["cl"], relegated=r["relegated"],
                    playoff=r["playoff"])


res = run(league, tuple(sorted(locked.items())), data.version())
s = res["summary"].join(table[["Pts", "P"]])

st.subheader("Chances by the end of the season")
cols = {"Club": s.index, "Now": s["Pts"].astype(int), "Expected pts": s["exp_pts"].round(0).astype(int),
        "Title": s["title"] * 100, "Champions League": s["cl"] * 100}
if rules["playoff"]:
    cols["Play-off"] = s["playoff"] * 100
cols["Relegated"] = s["relegated"] * 100
rule_text = f"Champions League = top {rules['cl']}. Relegated = bottom {rules['relegated']}."
if rules["playoff"]:
    rule_text += f" Play-off = {rules['playoff']}th, which plays a relegation play-off against a second-division side."
st.caption(rule_text + " Places can change with UEFA's coefficient rankings.")
show = pd.DataFrame(cols)
pct = st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)
st.dataframe(show, hide_index=True, width="stretch", height=38 + 35 * len(show),
             column_config={c: pct for c in list(cols)[3:]} | {
                            "Now": st.column_config.NumberColumn("Points now"),
                            "Expected pts": st.column_config.NumberColumn("Final pts (expected)")})

st.subheader("Where each club could finish")
pos = res["positions"].loc[s.index]
fig = px.imshow(pos.to_numpy(), x=[str(c) for c in pos.columns], y=pos.index.tolist(),
                color_continuous_scale="Greens", aspect="auto", zmin=0, zmax=float(pos.to_numpy().max()),
                labels=dict(x="Finishing position", y="", color="Chance"))
fig.update_traces(hovertemplate="%{y}: %{z:.0%} chance of finishing %{x}<extra></extra>")
fig.update_layout(height=30 * len(pos) + 20, margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False)
st.plotly_chart(fig, width="stretch")

with st.expander("Current table"):
    st.dataframe(table, width="stretch", hide_index=False)

ui.how_it_works("""
Each remaining game is played out using our win/draw/loss chances for it, based on each club's current
strength and form. Because nobody knows exactly how good a club really is, every simulated season also
nudges each club a little stronger or weaker for the rest of the year (think injuries, signings or a
new manager). Winning margins are drawn at random to settle goal-difference ties. Repeat
10,000 times, count the outcomes, and you get the percentages above. It can't see specific injuries or
transfers coming, so the further away the end of the season, the rougher the guide.
""")
