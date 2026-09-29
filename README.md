# FootyMinds

A simple web app for football fans covering **Europe's top five leagues** (Premier League, La Liga,
Serie A, Bundesliga, Ligue 1). Live at https://footyminds.streamlit.app.

| Page | Question it answers | How |
|---|---|---|
| This week | What's happening this gameweek/matchday? | Fixture cards with win/draw/loss chances, per league |
| Who wins? | Who's favourite, and why? | Logistic regression on Elo + rolling xG/shots/points form, pooled over ~18,000 games; "Why?" panel; public track record vs bookmakers |
| Where will they finish? | Title / Champions League / relegation odds | 10,000-season Monte Carlo with team-strength uncertainty and each league's rules (incl. Bundesliga/Ligue 1 play-offs); what-if mode |
| What's he worth? | Bargain or pricey? | Blend of per-league Ridge + pooled XGBoost on log market value from on-pitch stats (never sees previous price); SHAP "Why?" panel |
| Who plays like him? | Similar players anywhere in the top 5 | Per-90 profiles, cosine similarity within position, k-means playing styles |
| Head-to-head | Who's better at what? | Percentile radars + per-90 table |
| Fantasy picks | Who to pick / captain / transfer? (Premier League) | Expected FPL points by scoring rule; import any team by ID |

## Run it locally

Windows (Command Prompt or PowerShell):

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-pipeline.txt
python -m pipeline.run_all        &REM fetch data + train models (~5 min cold, ~1 min cached)
streamlit run streamlit_app.py
python -m pytest -q               &REM pipeline checks + every page renders, per league
```

macOS / Linux: same, but activate with `source .venv/bin/activate`.

## How it fits together

```
pipeline/config.py  league registry (LEAGUES): data-source codes, club counts, European/relegation places
pipeline/sources/   Understat · football-data.co.uk · Transfermarkt snapshot · FPL API (all free)
pipeline/clubs.py   learns club-name mappings from the data (same-day same-score matches; shared players)
pipeline/*.py       build_fixtures → build_matches → build_players → train_match → train_value
                    → build_scout → build_fpl        (orchestrated by run_all.py)
data/*.parquet      small precomputed artifacts the app reads (data/build/ holds big intermediates, not committed)
app/                Streamlit pages + shared UI; no training at runtime; app/clubs.csv holds club colours
```

- **Twice-weekly refresh:** `.github/workflows/refresh.yml` runs the pipeline on Tuesdays and Fridays, runs
  the tests, and commits the new `data/`. Streamlit Community Cloud redeploys on every push. If a run fails,
  or a source was down and last week's copy was used, the workflow opens a GitHub issue (which emails you).
- **Honest track record:** the match model only trains on completed seasons, so its predictions for the
  current season are out-of-sample.
- **Shareable links:** pickers are bound to the URL, e.g. `/value?player=Bukayo Saka · Arsenal`,
  `/match?home=Barcelona&away=Getafe` or `/table?league=Bundesliga`. Links without `league` mean the
  Premier League, unless they name a club from another league.

## Model scores (2025/26 season as a test; see `data/*_metrics.json`)

| League | Results called (model / bookmakers) | Player values: median error |
|---|---|---|
| Premier League | 48% / 49% | 27% |
| La Liga | 52% / 55% | 41% |
| Serie A | 53% / 54% | 32% |
| Bundesliga | 54% / 55% | 31% |
| Ligue 1 | 53% / 54% | 38% |

Match log-loss is within 0.011–0.021 of the bookmakers in every league. FPL expected points correlate 0.76
with FPL's own projection.

## Data caveats

- Opta pulled FBref's advanced stats in January 2026, so FBref isn't used.
- Defensive stats (tackles, interceptions, recoveries) and keeper saves come from the FPL API, so they exist
  for the Premier League only; cross-league scouting compares attacking and creative play.
- The free Transfermarkt dataset stopped updating in June 2026. Values are labelled "June 2026", and players
  at clubs promoted from second divisions often have none.
- Understat and FPL are unofficial sources: the pipeline caches everything and falls back to the last good
  copy if a source is down.

Not affiliated with any league, club, FPL, Understat or Transfermarkt. No club crests or league logos are
used. For fun and learning, not betting advice.
