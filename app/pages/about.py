import pandas as pd
import streamlit as st

from app import data

st.title("How it works")
m = data.meta("meta")
mm = data.meta("match_metrics")
vm = data.meta("value_metrics")

st.markdown(f"""
Matchday Lab turns free football data into answers fans actually care about. The data refreshes every
week{f" (last update: {pd.Timestamp(m['updated_at']).strftime('%d %B %Y')})" if m else ""}.

### Where the numbers come from
| What | Source |
|---|---|
| Player stats, prices, fixtures, FPL teams | Official Fantasy Premier League API |
| Expected goals (xG), shots, chances created | Understat |
| Results since 2016, shots, bookmaker odds | football-data.co.uk |
| Market values | Transfermarkt, via the open *transfermarkt-datasets* project (values as of {pd.Timestamp(vm.get('snapshot_date', '2026-06-12')).strftime('%d %B %Y')}) |

### How good are the predictions?
""")
if mm:
    ch = mm[mm["chosen"]]
    c1, c2, c3 = st.columns(3)
    c1.metric("Match results called correctly", f"{ch['accuracy']:.0%}",
              help=f"Tested on the whole {mm['validation_season']}/{str(mm['validation_season'] + 1)[-2:]} season")
    c2.metric("Bookmakers, same games", f"{mm['bookmaker']['accuracy']:.0%}")
    c3.metric("Guessing 'home win' every time", f"{mm['always_home_win']['accuracy']:.0%}")
if vm:
    v = vm[vm["chosen"]]
    st.markdown(f"**Player values:** half of our estimates are within **{v['median_pct_error']:.0f}%** of the "
                f"market value, and {v['within_50pct']:.0f}% are within 50%, tested on players the model "
                "hadn't seen.")

st.markdown("""
### Things to know
- These are **probabilities, not certainties**. A 60% favourite still fails to win 4 times in 10.
- The models don't know about injuries, suspensions or team news beyond what's in the FPL data.
- Newly promoted clubs have less data, so their predictions are less certain.
- Transfermarkt's free data stopped updating in June 2026, so newer signings may show old values
  or none at all.
- **This is for fun and learning. It is not betting advice.**

Not affiliated with the Premier League, Fantasy Premier League, Understat or Transfermarkt.
""")
