import numpy as np
import pandas as pd
import streamlit as st

from app import data, ui

PAGES = st.session_state["pages"]

st.title("Who plays *like him?*")
st.markdown("Pick a player to find others with the most similar playing style anywhere in Europe's top "
            "five leagues, based on what they do per 90 minutes.")

if not data.available("scout"):
    ui.missing("Scouting data")
    st.stop()

sc = data.table("scout")
meta = data.meta("scout_meta")
labels, full_stats, att_stats = meta["labels"], meta["style_stats"], meta["att_stats"]

pid = ui.player_picker("Player", sc.sort_values("win_minutes", ascending=False)["pid"].tolist(),
                       help=f"Players with at least {meta['min_minutes']} league minutes since last season. "
                            "Goalkeepers: Premier League only.")
if pid is None:
    st.stop()
me = sc.set_index("pid").loc[pid]

league = ui.league_filter("Search in", key="sc_league")
if me["pos"] == "GK" and league != "EPL":
    st.caption("Keepers can only be compared within the Premier League (that's where we have saves data).")
    league = "EPL"
# The full profile (with tackles, interceptions, recoveries) exists for Premier League players only.
full = me["league"] == "EPL" and league == "EPL"
cols = full_stats[me["pos"]] if full else att_stats[me["pos"]]
pct = "pct_" if full else "pct_eu_"
where = "Premier League" if full else "top-5-league"

with st.container(border=True, key="fmcard_player"):
    st.html(ui.club_stripe(me["team"]) + ui.player_header(me)
            + f'<div style="margin-top:.5rem">Playing style: {ui.pill(me["style"], ui.HOME)}</div>')
    strengths = sorted(((me[f"{pct}{c}"], labels[c]) for c in cols if pd.notna(me.get(f"{pct}{c}"))),
                       reverse=True)[:3]
    if strengths:
        st.markdown("Stands out for: " + ", ".join(
            f"**{lbl.lower()}** (better than {v:.0f}% of {where} {me['pos']}s)" for v, lbl in strengths))
if not full:
    st.caption("Across leagues we compare attacking and creative numbers (goals, expected goals, shots, "
               "chances created, involvement and build-up play). Defensive stats are only available for "
               "the Premier League: pick *Premier League* above to include them for Premier League players.")

with st.expander("Filters", expanded=False):
    f1, f2 = st.columns(2)
    max_age = f1.slider("Maximum age", 17, 40, 40, key="sc_age")
    budget = f2.select_slider("Maximum market value",
                              options=[5, 10, 20, 30, 50, 75, 100, 150, 250],
                              value=250, format_func=lambda v: "Any" if v == 250 else f"€{v}m", key="sc_budget")
    other_clubs = f1.toggle("Only other clubs", value=True, key="sc_other")
    any_pos = f2.toggle("Search all positions", value=False, key="sc_anypos",
                        help="Off: only players in the same position.")


def similar(sc: pd.DataFrame, pid: int, cols: list[str], same_pos: bool, league: str | None) -> pd.Series:
    me = sc.set_index("pid").loc[pid]
    pool = sc[sc["pos"] == me["pos"]] if same_pos or me["pos"] == "GK" else sc[sc["pos"] != "GK"]
    if league:
        pool = pool[(pool["league"] == league) | (pool["pid"] == pid)]
    pool = pool.dropna(subset=[f"p90_{c}" for c in cols])
    X = pool[[f"p90_{c}" for c in cols]].to_numpy(float)
    X = (X - X.mean(0)) / X.std(0).clip(1e-9)
    v = X[pool["pid"].tolist().index(pid)]
    cos = X @ v / (np.linalg.norm(X, axis=1).clip(1e-9) * np.linalg.norm(v).clip(1e-9))
    return pd.Series(np.clip(cos, 0, 1) * 100, index=pool["pid"])


sim = similar(sc, pid, cols, not any_pos, league).drop(pid)
res = sc.set_index("pid").loc[sim.index].assign(similarity=sim)
res = res[res["age"].isna() | (res["age"] <= max_age)]
if budget < 250:
    res = res[res["tm_value"].fillna(0) <= budget * 1e6]
if other_clubs:
    res = res[res["team"] != me["team"]]
res = res.sort_values("similarity", ascending=False).head(10)

ui.eyebrow("Look-alikes")
st.subheader(f"Most similar to {me['web_name']}")
if res.empty:
    st.info("No one matches those filters. Try loosening them.")
for c, r in res.iterrows():
    with st.container(border=True, key=f"fmcard_sim{c}"):
        a, b, d = st.columns([5, 2, 2], vertical_alignment="center")
        age = f"age {r['age']:.0f} · " if pd.notna(r["age"]) else ""
        a.html(f'<b>{r["name"]}</b><br><span class="ml-muted">{ui.badge(r["team"])} · {r["league_name"]} · '
               f'{r["pos"]} · {age}{r["style"]} · {ui.money(r["tm_value"])}</span>')
        b.html(ui.ring(r["similarity"], f"{r['similarity']:.0f}% similar"))
        d.page_link(PAGES["compare"], label="Compare", icon=":material/compare_arrows:",
                    query_params={"players": [data.player_label(pid), data.player_label(c)]})

with st.expander("What do the playing styles mean?"):
    st.markdown("We group players in each position by what they do most, using a clustering method "
                "(*k-means*). Premier League players are grouped using their full profile, including "
                "defensive work; players elsewhere by their attacking and creative numbers. A few typical "
                "players for each style:")
    g_all = sc if not league else sc[sc["league"] == league]
    for pos in ["GK", "DEF", "MID", "FWD"]:
        g = g_all[g_all["pos"] == pos]
        if g.empty:
            continue
        lines = [f"- **{s}**: " + ", ".join(grp.sort_values("win_minutes", ascending=False)["web_name"].head(4))
                 for s, grp in g.groupby("style")]
        st.markdown(f"**{pos}**\n" + "\n".join(lines))

ui.how_it_works("""
For every player we work out per-90-minute numbers over last season plus this one: goals, expected
goals, shots, chances created, involvement in attacks and build-up play for everyone (from Understat),
plus tackles, interceptions, recoveries and saves for Premier League players (from the Fantasy API).
We then compare the *shape* of each player's numbers with everyone else's in the same position.
100% would be an identical profile.
""")
