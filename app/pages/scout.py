import numpy as np
import pandas as pd
import streamlit as st

from app import data, ui

PAGES = st.session_state["pages"]

st.title("Who plays like him?")
st.markdown("Pick a player to find others with the most similar playing style, based on what they "
            "do per 90 minutes.")

if not data.available("scout"):
    ui.missing("Scouting data")
    st.stop()

sc = data.table("scout")
meta = data.meta("scout_meta")
labels, style_stats = meta["labels"], meta["style_stats"]

code = ui.player_picker("Player", sc.sort_values("win_minutes", ascending=False)["code"].tolist(),
                        help=f"Players with at least {meta['min_minutes']} league minutes since last season.")
if code is None:
    st.stop()
me = sc.set_index("code").loc[code]
cols = style_stats[me["pos"]]

with st.container(border=True):
    st.html(f'<div style="font-size:1.3rem;font-weight:700">{me["name"]}</div>'
            f'<div class="ml-muted">{ui.badge(me["team"])} · {me["pos"]} · age {me["age"]:.0f}</div>'
            f'<div style="margin-top:.5rem">Playing style: {ui.pill(me["style"], "#0E8A5F")}</div>')
    strengths = sorted(((me[f"pct_{c}"], labels[c]) for c in cols), reverse=True)[:3]
    st.markdown("Stands out for: " + ", ".join(f"**{l.lower()}** (better than {p:.0f}% of {me['pos']}s)"
                                              for p, l in strengths))

with st.expander("Filters", expanded=False):
    f1, f2 = st.columns(2)
    max_age = f1.slider("Maximum age", 17, 40, 40, key="sc_age")
    budget = f2.select_slider("Maximum market value",
                              options=[5, 10, 20, 30, 50, 75, 100, 150, 250],
                              value=250, format_func=lambda v: "Any" if v == 250 else f"€{v}m", key="sc_budget")
    other_clubs = f1.toggle("Only other clubs", value=True, key="sc_other")
    any_pos = f2.toggle("Search all positions", value=False, key="sc_anypos",
                        help="Off: only players in the same position.")


def similar(sc: pd.DataFrame, code: int, cols: list[str], same_pos: bool) -> pd.Series:
    me = sc.set_index("code").loc[code]
    pool = sc[sc["pos"] == me["pos"]] if same_pos else sc[sc["pos"] != "GK"] if me["pos"] != "GK" else sc[sc["pos"] == "GK"]
    X = pool[[f"p90_{c}" for c in cols]].to_numpy(float)
    X = (X - X.mean(0)) / X.std(0).clip(1e-9)
    v = X[pool["code"].tolist().index(code)]
    cos = X @ v / (np.linalg.norm(X, axis=1).clip(1e-9) * np.linalg.norm(v).clip(1e-9))
    return pd.Series(np.clip(cos, 0, 1) * 100, index=pool["code"])


sim = similar(sc, code, cols, not any_pos).drop(code)
res = sc.set_index("code").loc[sim.index].assign(similarity=sim)
res = res[res["age"] <= max_age]
if budget < 250:
    res = res[res["tm_value"].fillna(0) <= budget * 1e6]
if other_clubs:
    res = res[res["team"] != me["team"]]
res = res.sort_values("similarity", ascending=False).head(10)

st.subheader(f"Most similar to {me['web_name']}")
if res.empty:
    st.info("No one matches those filters. Try loosening them.")
for c, r in res.iterrows():
    with st.container(border=True):
        a, b, d = st.columns([5, 2, 2], vertical_alignment="center")
        a.html(f'<b>{r["name"]}</b><br><span class="ml-muted">{ui.badge(r["team"])} · {r["pos"]} · '
               f'age {r["age"]:.0f} · {r["style"]} · {ui.money(r["tm_value"])}</span>')
        b.metric("Similarity", f"{r['similarity']:.0f}%", label_visibility="collapsed")
        d.page_link(PAGES["compare"], label="Compare", icon=":material/compare_arrows:",
                    query_params={"players": [data.player_label(code), data.player_label(c)]})

with st.expander("What do the playing styles mean?"):
    st.markdown("We group players in each position by what they do most, using a clustering method "
                "(*k-means*). A few typical players for each style:")
    for pos in ["GK", "DEF", "MID", "FWD"]:
        g = sc[sc["pos"] == pos]
        lines = [f"- **{s}**: " + ", ".join(grp.sort_values("win_minutes", ascending=False)["web_name"].head(4))
                 for s, grp in g.groupby("style")]
        st.markdown(f"**{pos}**\n" + "\n".join(lines))

ui.how_it_works("""
For every player we work out per-90-minute numbers (goals, expected goals, shots, chances created,
build-up play, tackles, interceptions, recoveries; saves for keepers) over last season plus this one.
We then compare the *shape* of each player's numbers with everyone else's in the same position.
100% would be an identical profile. Numbers are from Understat and the official Fantasy API.
""")
