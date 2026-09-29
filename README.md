# Matchday Lab

A simple web app for Premier League fans that combines three ML projects (plus extras) in one place:

| Page | Question it answers | How |
|---|---|---|
| This week | What's happening this gameweek? | Fixture cards with win/draw/loss chances |
| Who wins? | Who's favourite, and why? | Logistic regression on Elo + rolling xG/shots/points form; "Why?" panel; public track record vs bookmakers |
| Where will they finish? | Title / top-4 / relegation odds | 10,000-season Monte Carlo with team-strength uncertainty; what-if mode |
| What's he worth? | Bargain or pricey? | Ridge regression on log market value from on-pitch stats (never sees previous price); SHAP "Why?" panel |
| Who plays like him? | Similar players | Per-90 profiles, cosine similarity within position, k-means playing styles |
| Head-to-head | Who's better at what? | Percentile radars + per-90 table |
| Fantasy picks | Who to pick / captain / transfer? | Expected FPL points by scoring rule; import any team by ID |

## Run it locally

Windows (Command Prompt or PowerShell):

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-pipeline.txt
python -m pipeline.run_all        &REM fetch data + train models (~2 min cold, ~10 s cached)
streamlit run streamlit_app.py
python -m pytest -q               &REM pipeline checks + every page renders
```

macOS / Linux: same, but activate with `source .venv/bin/activate`.

## How it fits together

```
pipeline/sources/   FPL API · Understat · football-data.co.uk · Transfermarkt snapshot (all free)
pipeline/*.py       build_players → build_matches → train_match → train_value → build_scout → build_fpl
data/*.parquet      small precomputed artifacts (~2 MB); the app only reads these
app/                Streamlit pages + shared UI; no training at runtime
```

- **Weekly refresh:** `.github/workflows/refresh.yml` runs the pipeline on Tuesdays and Fridays, runs the
  tests, and commits the new `data/`. Streamlit Community Cloud redeploys on every push.
- **Honest track record:** the match model only trains on completed seasons, so its predictions for the
  current season are out-of-sample.
- **Shareable links:** pickers are bound to the URL, e.g. `/value?player=Bukayo Saka · Arsenal` or
  `/match?home=Arsenal&away=Leeds`.

## Model scores (see `data/*_metrics.json`)

- Match results, tested on the whole 2025/26 season: 49% called correctly (bookmakers 49%); log-loss
  1.047 (bookmakers 1.019, base rates 1.085).
- Market value: median error 27% on unseen players; 80% within ±50%.
- FPL expected points correlate 0.78 with FPL's own projection.

## Data caveats

- Opta pulled FBref's advanced stats in January 2026, so FBref isn't used.
- The free Transfermarkt dataset stopped updating in June 2026. Values are labelled "June 2026",
  and players from outside the top divisions (e.g. newly promoted squads) often have none.
- FPL and Understat are unofficial sources: the pipeline caches everything and falls back to the last good
  copy if a source is down.

Not affiliated with the Premier League, FPL, Understat or Transfermarkt. No club crests or league logos are
used. For fun and learning, not betting advice.
