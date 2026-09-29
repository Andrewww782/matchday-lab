import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import data, ui
from app.fpl_live import FplError, squad

st.title("Fantasy picks")
st.markdown("Expected FPL points for every player over the next few gameweeks, based on their "
            "numbers, likely minutes and fixtures. Add your team ID for personal advice.")

if not data.available("fpl_players", "fpl_xpts"):
    ui.missing("Fantasy predictions")
    st.stop()

fp = data.table("fpl_players")
xp = data.table("fpl_xpts")
fmeta = data.meta("fpl_meta")
gw, horizon = fmeta["next_gw"], fmeta["horizon"]
short = data.short_names()
COMP_LABELS = {"appearance": "Playing", "goals": "Goals", "assists": "Assists", "clean_sheet": "Clean sheet",
               "conceded": "Goals conceded", "saves": "Saves", "defensive": "Defensive contribution",
               "bonus": "Bonus", "cards": "Cards"}
NEXT, FIVE = f"GW{gw} pts", f"Next {horizon} GWs"


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={"web_name": "Player", "team": "Club", "pos": "Pos", "price": "Price",
                              "selected_by_percent": "Owned", "xpts_next": NEXT, "xpts_5": FIVE})


cfg = {"Price": st.column_config.NumberColumn(format="£%.1fm"),
       "Owned": st.column_config.NumberColumn(format="%.1f%%"),
       NEXT: st.column_config.NumberColumn(format="%.1f"), FIVE: st.column_config.NumberColumn(format="%.1f")}

entry = st.text_input("Your FPL team ID (optional)", key="team", bind="query-params",
                      placeholder="e.g. 1234567",
                      help="On the FPL site, open 'Points'. The number after /entry/ in the web address is your ID.")

if entry.strip():
    if not entry.strip().isdigit():
        st.error("A team ID is just numbers, e.g. 1234567.")
    else:
        try:
            with st.spinner("Loading your team…"):
                sq = squad(int(entry), max(1, gw - 1))
        except FplError as e:
            st.error(str(e))
            sq = None
        if sq:
            picks = pd.DataFrame(sq["picks"])
            mine = picks.merge(fp, left_on="element", right_on="fpl_id", how="left")
            mine["Starting"] = mine["position"] <= 11
            st.subheader(sq["name"] or "Your team")

            xi = mine[mine["Starting"]].sort_values("xpts_next", ascending=False)
            cap, vice = xi.iloc[0], xi.iloc[1]
            c1, c2, c3 = st.columns(3)
            c1.metric("Captain pick", cap["web_name"], f"{cap['xpts_next']:.1f} expected pts", delta_color="off", delta_arrow="off")
            c2.metric("Vice-captain", vice["web_name"], f"{vice['xpts_next']:.1f} expected pts", delta_color="off", delta_arrow="off")
            c3.metric(f"Your XI in GW{gw}", f"{xi['xpts_next'].sum() + cap['xpts_next']:.0f} pts",
                      "including the captain's double", delta_color="off", delta_arrow="off")

            # Best single transfers: same position, affordable, respecting the 3-per-club rule.
            owned = set(mine["fpl_id"])
            clubs = mine["team"].value_counts()
            pool = fp[(~fp["fpl_id"].isin(owned)) & (fp["status"] == "a")]
            cands = []
            for o in mine.itertuples():
                budget = o.price + sq["bank"]
                ok = pool[(pool["pos"] == o.pos) & (pool["price"] <= budget + 1e-9)]
                ok = ok[ok["team"].map(lambda t: clubs.get(t, 0) - (t == o.team) < 3)]
                for b in ok.sort_values("xpts_5", ascending=False).head(5).itertuples():
                    gain = b.xpts_5 - o.xpts_5
                    # Bench upgrades only pay off when someone gets subbed off, so they count less.
                    cands.append({"Out": o.web_name + ("" if o.Starting else " (bench)"), "In": b.web_name,
                                  "In club": b.team, "Cost": b.price - o.price, "Gain": gain,
                                  "_rank": gain * (1 if o.Starting else 0.3)})
            ideas, used_in, used_out = [], set(), set()
            for c in sorted(cands, key=lambda c: -c["_rank"]):
                if c["Gain"] > 0.5 and c["In"] not in used_in and c["Out"] not in used_out:
                    ideas.append(c)
                    used_in.add(c["In"])
                    used_out.add(c["Out"])
            ideas = pd.DataFrame(ideas[:5]).drop(columns="_rank", errors="ignore")
            st.markdown(f"**Best transfers** (extra expected points over the next {horizon} gameweeks, "
                        f"with £{sq['bank']:.1f}m in the bank)")
            if len(ideas):
                ideas["Cost"] = ideas["Cost"].map(lambda c: "Same price" if abs(c) < 0.05 else f"{'-' if c < 0 else '+'}£{abs(c):.1f}m")
                st.dataframe(ideas, hide_index=True, width="stretch", column_config={
                    "Cost": st.column_config.TextColumn("Price change"),
                    "Gain": st.column_config.NumberColumn("Extra pts", format="+%.1f")})
                st.caption("Uses current prices: your selling price can be a little lower.")
            else:
                st.success("No clear upgrades. Your squad already looks strong for the coming weeks.")

            st.dataframe(tidy(mine.sort_values(["Starting", "xpts_next"], ascending=False))[
                             ["Player", "Club", "Pos", "Price", NEXT, FIVE, "Starting"]],
                         hide_index=True, width="stretch", column_config=cfg)
            st.divider()

tabs = st.tabs(["Top picks", "Differentials", "Fixtures", "Why this player?"])
with tabs[0]:
    pos = st.segmented_control("Position", ["All", "GK", "DEF", "MID", "FWD"], default="All", key="fpl_pos")
    max_price = st.slider("Max price (£m)", 4.0, 16.0, 16.0, 0.5, key="fpl_price")
    t = fp[(fp["price"] <= max_price) & (fp["status"] == "a")]
    if pos and pos != "All":
        t = t[t["pos"] == pos]
    st.dataframe(tidy(t.sort_values("xpts_5", ascending=False).head(25))[
                     ["Player", "Club", "Pos", "Price", "Owned", NEXT, FIVE]],
                 hide_index=True, width="stretch", column_config=cfg)
with tabs[1]:
    st.markdown("Players owned by **fewer than 10%** of managers who are expected to score well. "
                "Picking them helps you climb when they deliver.")
    d = fp[(fp["selected_by_percent"] < 10) & (fp["status"] == "a")].sort_values("xpts_5", ascending=False)
    st.dataframe(tidy(d.head(15))[["Player", "Club", "Pos", "Price", "Owned", NEXT, FIVE]],
                 hide_index=True, width="stretch", column_config=cfg)
with tabs[2]:
    st.markdown(f"Each club's chance of **winning** its games in the next {horizon} gameweeks. Greener = easier.")
    ff = data.table("fpl_fixtures")
    rows = []
    for f in ff.itertuples():
        rows.append((f.home, f.gw, f"{short.get(f.away, f.away)} (H)", f.p_h))
        rows.append((f.away, f.gw, f"{short.get(f.home, f.home)} (A)", f.p_a))
    g = pd.DataFrame(rows, columns=["team", "gw", "opp", "win"])
    g = g.groupby(["team", "gw"]).agg(opp=("opp", " + ".join), win=("win", "mean")).reset_index()
    order = g.groupby("team")["win"].mean().sort_values(ascending=False).index
    gws = sorted(g["gw"].unique())
    z = g.pivot(index="team", columns="gw", values="win").reindex(index=order, columns=gws)
    txt = g.pivot(index="team", columns="gw", values="opp").reindex(index=order, columns=gws).fillna("—")
    fig = go.Figure(go.Heatmap(z=z.to_numpy(), x=[f"GW{c}" for c in gws], y=list(order), text=txt.to_numpy(),
                               texttemplate="%{text}", colorscale="RdYlGn", zmin=0.1, zmax=0.7, showscale=False,
                               hovertemplate="%{y} %{x}: %{text}<br>Win chance %{z:.0%}<extra></extra>"))
    fig.update_layout(height=640, margin=dict(l=0, r=0, t=10, b=0), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch")
with tabs[3]:
    labels = fp.set_index("code")["name"] + " · " + fp.set_index("code")["team"]
    choices = fp.sort_values("xpts_5", ascending=False)["code"].tolist()
    who = st.selectbox("Player", choices, format_func=lambda c: labels.get(c, str(c)), key="fpl_why")
    rows = xp[xp["code"] == who]
    if rows.empty:
        st.info("No fixtures in the next few gameweeks.")
    else:
        comp = rows[list(COMP_LABELS)].sum().rename(COMP_LABELS)
        comp = comp[comp.abs() >= 0.05].sort_values()
        st.markdown(f"**{rows['xpts'].sum():.1f} expected points over the next {horizon} gameweeks.** "
                    f"Expected minutes per game: {rows['exp_min'].mean():.0f}.")
        fig = go.Figure(go.Bar(x=comp.values, y=comp.index, orientation="h",
                               marker_color=["#0E8A5F" if v > 0 else "#C2410C" for v in comp.values],
                               hovertemplate="%{y}: %{x:.1f} pts<extra></extra>"))
        fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0), xaxis_title="Expected points")
        st.plotly_chart(fig, width="stretch")
        per = rows.assign(Fixture=rows["opp"].map(lambda t: short.get(t, t)) + " (" + rows["venue"] + ")")
        st.dataframe(per[["gw", "Fixture", "xpts"]].rename(columns={"gw": "GW", "xpts": "Expected pts"}),
                     hide_index=True, width="stretch")

ui.how_it_works("""
For each player we estimate **minutes** (recent playing time and injury news), then add up the points
he's expected to earn from each FPL scoring rule: goals and assists (from expected goals and assists
per 90), clean sheets and goals conceded (from how many goals the opponent is expected to score),
saves, defensive contributions, bonus and cards. Stronger opponents lower the attacking numbers,
weaker ones raise them. The official FPL scoring rules are read straight from the game.
""")
