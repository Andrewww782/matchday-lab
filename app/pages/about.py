import pandas as pd
import streamlit as st

from app import data

st.title("How it *works*")
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
| Premier League only: tackles, interceptions, saves | Official Fantasy Premier League API |
| Fan VAR: cards, penalties, VAR decisions, referees, line-ups | ESPN match commentary (all five leagues) |
| Fan VAR highlights | Official league channels on YouTube |
""")

st.markdown("### Coverage and accuracy by league")
lg = data.leagues()
gm = data.meta("goals_metrics")
head = mm.get("headline", mm)
by_match, by_value, by_goals = head.get("by_league", {}), vm.get("by_league", {}), gm.get("by_league", {})
rows = []
for k, cfg in lg.items():
    bm, bv, bg = by_match.get(k, {}), by_value.get(k, {}), by_goals.get(k, {})
    rows.append({
        "League": cfg["name"],
        "Results called (us / bookies)": f"{bm['model']['accuracy']:.0%} / {bm['bookmaker']['accuracy']:.0%}" if bm else "–",
        "Over/under 2.5 (us / bookies)": f"{bg['over25_accuracy']:.0%} / {bg['over25_accuracy_bookmaker']:.0%}" if bg else "–",
        "Exact score in our top 3": f"{bg['top3_hit']:.0%}" if bg else "–",
        "Player values: typical error": f"{bv['median_pct_error']:.0f}%" if bv else "–",
        "Defensive stats & keepers": "Yes" if k == "EPL" else "No",
    })
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.caption("All tested on the whole 2025/26 season, using only games before each one. \"Results called\" "
           "means the outcome we rated most likely happened. \"Typical error\" is the median gap between our "
           "value and Transfermarkt's.")

if head.get("by_league", {}).get("all"):
    a = head["by_league"]["all"]
    c1, c2, c3 = st.columns(3)
    c1.metric("All five leagues: results called", f"{a['model']['accuracy']:.0%}")
    c2.metric("Bookmakers, same games", f"{a['bookmaker']['accuracy']:.0%}")
    c3.metric("Guessing 'home win' every time", f"{mm['always_home_win']['accuracy']:.0%}")

st.markdown("""
### How Fan VAR works
- After every round we read each match's live commentary and pick out the calls fans argue about:
  **penalties, red cards, VAR checks and goals ruled out**. Yellow cards are there too, under *Every match*.
- **You vote**: right call or wrong call, and, if wrong, what it should have been. One vote per call per
  device, no sign-up, and you can change your mind.
- **Fan flags**: if the ref missed something, flag it. Once three fans flag the same moment, it becomes a call
  everyone votes on. Flags use set choices only (no free text), so there's nothing to moderate.
- **Verdicts**: "howler" means at least 3 in 4 fans say wrong; "split" means close to 50/50. The referee
  report card and "Who gets robbed?" only count calls with at least 5 votes.
- Your device id is a random code in a cookie. We never ask who you are.

### Things to know
- These are **probabilities, not certainties**. A 60% favourite still fails to win 4 times in 10, and
  even the single most likely scoreline usually happens only about 1 time in 8.
- The models don't know about injuries or suspensions beyond what's in the data.
- Newly promoted clubs have less data, so their predictions and player values are less certain.
  Players at clubs promoted from second divisions often have no Transfermarkt value in the free data.
- Outside the Premier League we don't have defensive stats (tackles, interceptions) or keeper saves,
  so cross-league scouting compares attacking and creative play.
- Transfermarkt's free data stopped updating in June 2026, so newer signings may show old values or none.
- **This is for fun and learning. It is not betting advice.**

Not affiliated with any league, club, Fantasy Premier League, Understat or Transfermarkt.
""")
