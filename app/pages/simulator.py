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

fx = data.table("fixtures")
teams = data.teams()
table = current_table(fx, teams)
remaining = data.table("upcoming").set_index("fixture_id")

locked: dict = st.session_state.setdefault("whatif", {})

with st.expander("What if…? Lock in some results", expanded=bool(locked)):
    gws = sorted(remaining["gw"].unique())
    gw = st.selectbox("Gameweek", gws, format_func=lambda g: f"Gameweek {g}", key="sim_gw")
    view = remaining[remaining["gw"] == gw].sort_values("kickoff")
    RES = {"Model decides": None, "Home win": "H", "Draw": "D", "Away win": "A"}
    INV = {v: k for k, v in RES.items()}
    ed = pd.DataFrame({"Home": view["home"], "Away": view["away"],
                       "Result": [INV[locked.get(i)] for i in view.index]}, index=view.index)
    out = st.data_editor(ed, hide_index=True, width="stretch", key=f"sim_edit_{gw}",
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


@st.cache_data(ttl=3600, max_entries=64)
def run(locked_items: tuple) -> dict:
    return simulate(table, remaining, locked=dict(locked_items))


res = run(tuple(sorted(locked.items())))
s = res["summary"].join(table[["Pts", "P"]])

st.subheader("Chances by the end of the season")
show = pd.DataFrame({
    "Club": s.index, "Now": s["Pts"].astype(int), "Expected pts": s["exp_pts"].round(0).astype(int),
    "Win the league": s["title"] * 100, "Top 4": s["top4"] * 100, "Top 5": s["top5"] * 100,
    "Relegated": s["relegated"] * 100,
})
pct = st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=100)
st.dataframe(show, hide_index=True, width="stretch", height=740,
             column_config={"Win the league": pct, "Top 4": pct, "Top 5": pct, "Relegated": pct,
                            "Now": st.column_config.NumberColumn("Points now"),
                            "Expected pts": st.column_config.NumberColumn("Expected final points")})

st.subheader("Where each club could finish")
pos = res["positions"].loc[s.index]
fig = px.imshow(pos.to_numpy(), x=[str(c) for c in pos.columns], y=pos.index.tolist(),
                color_continuous_scale="Greens", aspect="auto", zmin=0, zmax=float(pos.to_numpy().max()),
                labels=dict(x="Finishing position", y="", color="Chance"))
fig.update_traces(hovertemplate="%{y}: %{z:.0%} chance of finishing %{x}<extra></extra>")
fig.update_layout(height=620, margin=dict(l=0, r=0, t=10, b=0), coloraxis_showscale=False)
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
