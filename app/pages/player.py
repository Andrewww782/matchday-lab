import pandas as pd
import streamlit as st

from app import data, theme, ui

PAGES = st.session_state["pages"]

st.title("Player *profile*")
st.markdown("Any player in Europe's top five leagues: his form, his value, his style, and where to "
            "go for the full breakdown.")

if not data.available("players"):
    ui.missing("Player profiles")
    st.stop()

players = data.table("players").set_index("pid")
pid = ui.player_picker("Player", data.player_index()["pid"].tolist(),
                       help="Players in Europe's top 5 leagues with at least some minutes this "
                            "season or last.")
if pid is None:
    st.stop()
p = players.loc[pid]
label = data.player_label(pid)

with st.container(border=True, key="fmcard_player"):
    st.html(ui.club_stripe(p["team"]) + ui.player_header(p)
            + (f'<div class="ml-muted">Contract to {pd.Timestamp(p["contract_expiration_date"]).year}</div>'
               if pd.notna(p.get("contract_expiration_date")) else ""))

VERDICT_COLOUR = {"Bargain": theme.GOOD, "Fair price": theme.NEUTRAL, "Pricey": theme.BAD,
                  "No market value": theme.NEUTRAL}
if data.available("values"):
    vals = data.table("values").set_index("pid")
    if pid in vals.index:
        v = vals.loc[pid]
        ui.eyebrow("Value")
        st.subheader("What's he worth?")
        k1, k2, k3 = st.columns(3)
        k1.metric("His numbers say", ui.money(v["est_value"]))
        k2.metric("Market value", ui.money(v["tm_value"]))
        with k3:
            st.markdown("Verdict")
            st.html(ui.pill(v["verdict"], VERDICT_COLOUR.get(v["verdict"], "#888"),
                            shine=v["verdict"] == "Bargain"))
        st.page_link(PAGES["value"], label="Full value breakdown", icon=":material/payments:",
                     query_params={"player": label})

if data.available("scout"):
    sc = data.table("scout").set_index("pid")
    if pid in sc.index:
        me = sc.loc[pid]
        meta = data.meta("scout_meta")
        labels_, full_stats, att_stats = meta["labels"], meta["style_stats"], meta["att_stats"]
        full = me["league"] == "EPL"
        cols = full_stats[me["pos"]] if full else att_stats[me["pos"]]
        pct = "pct_" if full else "pct_eu_"
        where = "Premier League" if full else "top-5-league"
        strengths = sorted(((me[f"{pct}{c}"], labels_[c]) for c in cols if pd.notna(me.get(f"{pct}{c}"))),
                           reverse=True)[:2]
        ui.eyebrow("Style")
        st.subheader("Playing style")
        st.html(f"Style: {ui.pill(me['style'], ui.HOME)}")
        if strengths:
            st.markdown("Stands out for: " + ", ".join(
                f"**{lbl.lower()}** (better than {v:.0f}% of {where} {me['pos']}s)" for v, lbl in strengths))
        st.page_link(PAGES["scout"], label="Full style profile", icon=":material/person_search:",
                     query_params={"player": label})

ui.eyebrow("This season")
st.subheader("At a glance")
m1, m2, m3 = st.columns(3)
m1.metric("Minutes", f"{p['win_minutes']:.0f}" if pd.notna(p["win_minutes"]) else "–")
m2.metric("Non-penalty goals", f"{p['win_npg']:.1f}" if pd.notna(p["win_npg"]) else "–")
m3.metric("Expected assists (xA)", f"{p['win_xA']:.1f}" if pd.notna(p["win_xA"]) else "–")
st.caption("Over the last season plus this one, so early-season numbers aren't dominated by a "
          "handful of games.")

st.divider()
ui.eyebrow("Go deeper")
c1, c2, c3 = st.columns(3)
c1.page_link(PAGES["value"], label="What's he worth?", icon=":material/payments:", query_params={"player": label})
c2.page_link(PAGES["scout"], label="Similar players", icon=":material/person_search:", query_params={"player": label})
c3.page_link(PAGES["compare"], label="Compare him", icon=":material/compare_arrows:",
            query_params={"players": label})
