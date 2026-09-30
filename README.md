# FootyMinds

A simple web app for football fans covering **Europe's top five leagues** (Premier League, La Liga,
Serie A, Bundesliga, Ligue 1). Live at https://footyminds.streamlit.app.

| Page | Question it answers | How |
|---|---|---|
| **Fan VAR** (headline act) | Did the ref get it right? | Every penalty, red card, VAR check and ruled-out goal in all five leagues (parsed from ESPN match commentary, daily); fans vote right/wrong call (one vote per device, no sign-up), flag missed incidents, and see fans-vs-neutrals splits, a referee report card and "Who gets robbed?"; official highlights embedded from YouTube |
| Offside check | Was it offside? | Upload a screenshot (or try the demo): players spotted by YOLOX (ONNX on CPU, Apache-2.0), you pick attacker + last defender and two lines parallel to the goal line; the vanishing point gives true-perspective offside lines. Optional: 4 box corners → gap in cm, top-down map, 3D view. Linked from Fan VAR goal calls |
| This week | What's happening this gameweek/matchday? | Hottest Fan VAR calls, then fixture cards with win/draw/loss chances, per league |
| Who wins? | Who's favourite, what's the score, and why? | Blend of a form model (Elo + rolling xG/shots/points, ~18,000 games) and a Dixon-Coles goals model; scorelines, both-teams-to-score, over 2.5, clean sheets; "Why?" panel; public track record vs bookmakers |
| Where will they finish? | Title / Champions League / relegation odds | 10,000-season Monte Carlo with team-strength uncertainty and each league's rules (incl. Bundesliga/Ligue 1 play-offs); what-if mode |
| What's he worth? | Bargain or pricey? | Blend of per-league Ridge + pooled XGBoost on log market value from on-pitch stats (never sees previous price); SHAP "Why?" panel |
| Who plays like him? | Similar players anywhere in the top 5 | Per-90 profiles, cosine similarity within position, k-means playing styles |
| Head-to-head | Who's better at what? | Percentile radars + per-90 table |

Fantasy picks (expected FPL points) still builds every refresh but is **parked**: hidden from the menu until a later update.

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

## Fan VAR setup (one-time, free, personal accounts)

Without these the site still works: votes go to a local SQLite file and highlights become a YouTube search link.

1. **Votes database (Neon Postgres, free tier).** Create a project at neon.tech, copy the connection string, and add it
   in Streamlit Cloud → your app → Settings → Secrets (and in a local, gitignored `.streamlit/secrets.toml`):
   ```toml
   [connections.fanvar]
   url = "postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require"
   ```
   Tables are created automatically on first use.
2. **Highlights (YouTube Data API, free quota).** In a Google Cloud project enable *YouTube Data API v3*, create an
   API key, and add it to the GitHub repo as the Actions secret `YOUTUBE_API_KEY`. The daily workflow
   (`.github/workflows/incidents.yml`) then finds each match's official highlights.

## How it fits together

```
pipeline/config.py  league registry (LEAGUES): data-source codes, club counts, European/relegation places
pipeline/sources/   Understat · football-data.co.uk · Transfermarkt snapshot · FPL API (all free)
pipeline/clubs.py   learns club-name mappings from the data (same-day same-score matches; shared players)
pipeline/*.py       build_fixtures → build_matches → build_players → train_match → train_goals → train_value
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

| League | Results called (us / bookmakers) | Over/under 2.5 (us / bookmakers) | Exact score in our top 3 | Player values: median error |
|---|---|---|---|---|
| Premier League | 49% / 49% | 55% / 55% | 32% | 27% |
| La Liga | 52% / 55% | 53% / 57% | 39% | 40% |
| Serie A | 52% / 54% | 53% / 53% | 37% | 32% |
| Bundesliga | 55% / 55% | 61% / 61% | 26% | 32% |
| Ligue 1 | 53% / 54% | 56% / 63% | 30% | 39% |

- **Results** are an average of the form model (Elo + rolling form, logistic regression) and the goals model;
  the blend beat either alone in every league, and sits within 0.007–0.012 log-loss of the bookmakers.
- **Scorelines** come from a Dixon-Coles-style goals model per league (weighted Poisson on 80% xG / 20% goals,
  480-day half-life, scoring level calibrated to the last 200 real games, low-score correction). Predicted
  goals per game are within 0.11 of the real 2025/26 averages in every league.
- In low-scoring 2025/26 Serie A, neither we nor the bookmakers beat simply using last season's over-2.5 rate.
- FPL expected points correlate 0.78 with FPL's own projection.

## Data caveats

- Opta pulled FBref's advanced stats in January 2026, so FBref isn't used.
- Defensive stats (tackles, interceptions, recoveries) and keeper saves come from the FPL API, so they exist
  for the Premier League only; cross-league scouting compares attacking and creative play.
- The free Transfermarkt dataset stopped updating in June 2026. Values are labelled "June 2026", and players
  at clubs promoted from second divisions often have none.
- Understat and FPL are unofficial sources: the pipeline caches everything and falls back to the last good
  copy if a source is down.

Not affiliated with any league, club, FPL, Understat or Transfermarkt. Demo photo for the offside check: Roger Cornfoot, CC BY-SA 2.0 (Wikimedia Commons). Player detection: YOLOX by Megvii, Apache-2.0. No club crests or league logos are
used. For fun and learning, not betting advice.
