import pandas as pd
import streamlit as st

from app import data

st.title("How it works")
m = data.meta("meta")
mm = data.meta("match_metrics")
vm = data.meta("value_metrics")
snap = pd.Timestamp(vm.get("snapshot_date", "2026-06-12")).strftime("%d %B %Y")

st.markdown(f"""
FootyMinds turns free football data into answers fans actually care about, for Europe's top five
leagues. The data refreshes twice a week{f" (last update: {pd.Timestamp(m['updated_at']).strftime('%d %B %Y')})" if m else ""}.

### Where the numbers come from
| What | Source |
|---|---|
| Expected goals (xG), shots, chances created, fixtures | Understat (all five leagues) |
| Results since 2016, shots, bookmaker odds | football-data.co.uk |
| Market values | Transfermarkt, via the open *transfermarkt-datasets* project (values as of {snap}) |
| Premier League only: prices, tackles, interceptions, saves, FPL teams | Official Fantasy Premier League API |
""")

st.markdown("### Coverage and accuracy by league")
lg = data.leagues()
by_match = mm.get("by_league", {})
by_value = vm.get("by_league", {})
rows = []
for k, cfg in lg.items():
    bm, bv = by_match.get(k, {}), by_value.get(k, {})
    rows.append({
        "League": cfg["name"],
        "Results called (last season)": f"{bm['model']['accuracy']:.0%}" if bm else "–",
        "Bookmakers": f"{bm['bookmaker']['accuracy']:.0%}" if bm else "–",
        "Player values: typical error": f"{bv['median_pct_error']:.0f}%" if bv else "–",
        "Defensive stats & keepers": "Yes" if k == "EPL" else "No",
        "Fantasy (FPL)": "Yes" if k == "EPL" else "No",
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption("\"Results called\" means the outcome we rated most likely actually happened, tested on the "
           "whole 2025/26 season. \"Typical error\" is the median gap between our value and Transfermarkt's.")

if mm:
    ch = mm[mm["chosen"]]
    c1, c2, c3 = st.columns(3)
    c1.metric("All five leagues: results called", f"{ch['accuracy']:.0%}")
    c2.metric("Bookmakers, same games", f"{mm['bookmaker']['accuracy']:.0%}")
    c3.metric("Guessing 'home win' every time", f"{mm['always_home_win']['accuracy']:.0%}")

st.markdown("""
### Things to know
- These are **probabilities, not certainties**. A 60% favourite still fails to win 4 times in 10.
- The models don't know about injuries or suspensions beyond what's in the data.
- Newly promoted clubs have less data, so their predictions and player values are less certain.
  Players at clubs promoted from second divisions often have no Transfermarkt value in the free data.
- Outside the Premier League we don't have defensive stats (tackles, interceptions) or keeper saves,
  so cross-league scouting compares attacking and creative play.
- Transfermarkt's free data stopped updating in June 2026, so newer signings may show old values or none.
- **This is for fun and learning. It is not betting advice.**

Not affiliated with any league, club, Fantasy Premier League, Understat or Transfermarkt.
""")
