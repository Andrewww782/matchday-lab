import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from app import data, ui

st.title("Head-to-head")
st.markdown("Put up to three players side by side. Scores are percentiles: 90 means better than 90% "
            "of players in his position.")

if not data.available("scout"):
    ui.missing("Player stats")
    st.stop()

sc = data.table("scout")
meta = data.meta("scout_meta")
labels, style_stats = meta["labels"], meta["style_stats"]
idx = data.player_index().set_index("code")["label"].to_dict()
codes = [c for c in sc.sort_values("win_minutes", ascending=False)["code"] if c in idx]

picked = st.multiselect("Players", codes, max_selections=3, key="players", bind="query-params",
                        format_func=lambda c: idx.get(c, str(c)), placeholder="Type a player's name…",
                        default=codes[:2] if "players" not in st.query_params else None)
if len(picked) < 2:
    st.info("Pick at least two players to compare.")
    st.stop()

rows = sc.set_index("code").loc[picked]
pos_list = rows["pos"].unique().tolist()
if "GK" in pos_list and len(pos_list) > 1:
    st.warning("Goalkeepers are measured differently from outfield players, so this comparison "
               "won't say much.")
stats = style_stats[rows["pos"].iloc[0]] if len(pos_list) == 1 else \
    list(dict.fromkeys(sum((style_stats[p] for p in pos_list if p != "GK"), [])))

COLOURS = ["#0E8A5F", "#3F6FD8", "#D97706"]
fig = go.Figure()
theta = [labels[s] for s in stats]
for (c, r), colour in zip(rows.iterrows(), COLOURS):
    vals = [r[f"pct_{s}"] for s in stats]
    fig.add_trace(go.Scatterpolar(r=vals + vals[:1], theta=theta + theta[:1], name=r["web_name"],
                                  fill="toself", line=dict(color=colour, width=2), opacity=0.55,
                                  hovertemplate="%{theta}: %{r:.0f}<extra>" + r["web_name"] + "</extra>"))
fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], showticklabels=False, ticks="")),
                  legend=dict(orientation="h", y=-0.1), margin=dict(l=40, r=40, t=20, b=20), height=460)
st.plotly_chart(fig, width="stretch")

# Stat-by-stat table, per 90 minutes, with the leader marked.
table = pd.DataFrame({r["web_name"]: [r[f"p90_{s}"] for s in stats] for _, r in rows.iterrows()},
                     index=[labels[s] for s in stats])
leader = table.idxmax(axis=1)
wins = leader.value_counts()
summary = ", ".join(f"**{n}** leads on {k}" for n, k in wins.items())
st.markdown(f"Per 90 minutes: {summary} of {len(stats)} measures.")
show = table.round(2).astype(str)
for stat, who in leader.items():
    show.loc[stat, who] = "🟢 " + show.loc[stat, who]
info = pd.DataFrame({r["web_name"]: [r["team"], r["style"], f"{r['age']:.0f}", f"{r['win_minutes']:.0f}",
                                     ui.money(r["tm_value"])] for _, r in rows.iterrows()},
                    index=["Club", "Style", "Age", "Minutes (since last season)", "Market value"])
st.dataframe(pd.concat([info, show]), width="stretch")
