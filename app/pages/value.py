import pandas as pd
import streamlit as st

from app import data, ui

st.title("What's he worth?")
st.markdown("What a player's numbers say he's worth, next to his market value.")

if not data.available("values", "players"):
    ui.missing("Player values")
    st.stop()

vals = data.table("values")
players = data.table("players").set_index("pid")
vm = data.meta("value_metrics")
snap = pd.Timestamp(vm.get("snapshot_date", "2026-06-12")).strftime("%B %Y")
GROUPS = [c for c in vals.columns if c not in ("pid", "league", "est_value", "tm_value", "value_ratio", "verdict")]
VERDICT_COLOUR = {"Bargain": "#0E8A5F", "Fair price": "#8A948F", "Pricey": "#C2410C", "No market value": "#8A948F"}

pids = vals.sort_values("est_value", ascending=False)["pid"].tolist()
pid = ui.player_picker("Player", pids, help="Players in Europe's top 5 leagues with at least 450 league "
                                            "minutes since last season.")
if pid is None:
    st.stop()

v = vals.set_index("pid").loc[pid]
p = players.loc[pid]

with st.container(border=True):
    st.html(f'<div style="font-size:1.3rem;font-weight:700">{p["name"]}</div>'
            f'<div class="ml-muted">{ui.badge(p["team"])} · {p["league_name"]} · {p.get("sub_position") or p["pos"]} · '
            f'age {p["age"]:.0f}'
            + (f' · contract to {pd.Timestamp(p["contract_expiration_date"]).year}'
               if pd.notna(p.get("contract_expiration_date")) else "") + "</div>")
    k1, k2, k3 = st.columns(3)
    k1.metric("His numbers say", ui.money(v["est_value"]))
    k2.metric(f"Market value ({snap})", ui.money(v["tm_value"]),
              help="Transfermarkt's valuation. Their free data stopped updating in June 2026.")
    with k3:
        st.markdown("Verdict")
        st.html(ui.pill(v["verdict"], VERDICT_COLOUR.get(v["verdict"], "#888")))
        if pd.notna(v["value_ratio"]):
            gap = v["value_ratio"] - 1
            st.caption(f"Stats suggest {abs(gap):.0%} {'more' if gap > 0 else 'less'} than the market")

st.subheader("Why?")
items = sorted([(g, float(v[g])) for g in GROUPS if abs(v[g]) >= 2], key=lambda x: -abs(x[1]))
if items:
    up = [g.lower() for g, x in items if x > 0][:2]
    down = [g.lower() for g, x in items if x < 0][:2]
    parts = []
    if up:
        parts.append(f"his value is pushed up by **{' and '.join(up)}**")
    if down:
        parts.append(f"held back by **{' and '.join(down)}**")
    st.markdown("Compared with an average player in Europe's top 5 leagues, " + ", ".join(parts) + ".")
    st.html(ui.why_bars(items, "Lowers value", "Raises value", unit="%"))
    st.caption("Each bar shows roughly how much that factor raises or lowers his estimate compared "
               "with an average player.")

ui.how_it_works(f"""
We trained a model on four seasons of players from Europe's top five leagues ({len(vals)} are
rated right now), using only what happens on the pitch: **age, position, playing time, goals and
chances, creativity, build-up play, how good his team is and which league he plays in** (the same
numbers are worth more in some leagues than others). It never sees his previous price, so the gap
between our number and the market is the interesting part.

- **Bargain**: his numbers suggest he's worth at least a third more than the market says.
- **Pricey**: the market values him well above what his numbers alone suggest. Often that's for
  things stats can't see: potential, reputation, leadership or marketing.

Half of its estimates are within about
{vm.get('by_league', {}).get(p['league'], {}).get('median_pct_error', 30):.0f}% of the market value in the
{p['league_name']}. It's weakest for goalkeepers and teenagers.
""")

st.divider()
st.subheader("Bargains and pricey players")
lg = ui.league_filter(key="vleague")
pos = st.segmented_control("Position", ["All", "GK", "DEF", "MID", "FWD"], default="All", key="vpos")
tbl = vals[vals["tm_value"].notna()].drop(columns=GROUPS + ["league"]).merge(
    players[["name", "team", "league", "pos", "age"]], left_on="pid", right_index=True)
if lg:
    tbl = tbl[tbl["league"] == lg]
if pos and pos != "All":
    tbl = tbl[tbl["pos"] == pos]
tbl = tbl.assign(**{"Our estimate": tbl["est_value"].map(ui.money), "Market": tbl["tm_value"].map(ui.money),
                    "Gap": (tbl["value_ratio"] - 1)})
cols = {"name": "Player", "team": "Club", "age": "Age"}
t1, t2 = st.tabs(["Biggest bargains", "Most pricey"])
fmt = {"Gap": st.column_config.NumberColumn(format="percent"),
       "Age": st.column_config.NumberColumn(format="%.0f")}
with t1:
    st.dataframe(tbl.sort_values("value_ratio", ascending=False).head(15)
                 .rename(columns=cols)[["Player", "Club", "Age", "Our estimate", "Market", "Gap"]],
                 hide_index=True, width="stretch", column_config=fmt)
with t2:
    st.dataframe(tbl.sort_values("value_ratio").head(15)
                 .rename(columns=cols)[["Player", "Club", "Age", "Our estimate", "Market", "Gap"]],
                 hide_index=True, width="stretch", column_config=fmt)
