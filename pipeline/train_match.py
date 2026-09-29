"""Train the match outcome model, score it against the bookmakers, and precompute
predictions + explanations for every pairing of current clubs.

The production model only ever sees *completed* seasons, so its predictions for the
current season are genuinely out-of-sample - that's the public track record."""
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from pipeline import build_matches as bm
from pipeline.config import CURRENT_SEASON, DATA, LEAGUES, MODELS

CLASSES = ["H", "D", "A"]
FORM = bm.form_columns()
# League flags let home advantage and draw rates differ by league (EPL is the baseline).
LEAGUE_FEATS = [f"lg_{k}" for k in LEAGUES if k != "EPL"]
FEATURES = ["elo_diff"] + [f"d_{c}" for c in FORM] + ["h_rest_days", "a_rest_days"] + LEAGUE_FEATS

# Fan-friendly groups for the "Why?" panel.
GROUPS = {
    "Overall team strength": ["elo_diff"],
    "Recent chance creation (xG)": [c for c in FEATURES if c.startswith("d_xgf")],
    "Recent chances conceded (xG against)": [c for c in FEATURES if c.startswith("d_xga")],
    "Recent goals scored & conceded": [c for c in FEATURES if c.startswith(("d_gf", "d_ga"))],
    "Recent shots": [c for c in FEATURES if c.startswith(("d_sf", "d_sa", "d_sot"))],
    "Recent results": [c for c in FEATURES if c.startswith("d_pts")],
    "Rest between games": ["h_rest_days", "a_rest_days"],
}
NEUTRAL_REST = 7.0


def make_features(df: pd.DataFrame, fill: dict) -> pd.DataFrame:
    """Home-minus-away differences. `fill` holds per-stat priors for clubs with no recent form."""
    X = pd.DataFrame(index=df.index)
    X["elo_diff"] = df["home_elo"] - df["away_elo"]
    for c in FORM:
        X[f"d_{c}"] = df[f"h_{c}"].fillna(fill[c]) - df[f"a_{c}"].fillna(fill[c])
    X["h_rest_days"] = df["h_rest_days"].fillna(NEUTRAL_REST)
    X["a_rest_days"] = df["a_rest_days"].fillna(NEUTRAL_REST)
    for f in LEAGUE_FEATS:
        X[f] = (df["league"] == f[3:]).astype(float)
    return X[FEATURES]


def promoted_prior(long: pd.DataFrame, seasons: list[int]) -> dict:
    """Typical form of a newly promoted club in its first 10 games (used when form is unknown)."""
    t = long[long.season.isin(seasons)].copy()
    t["n"] = t.groupby(["team", "stint"]).cumcount()
    first = t.groupby(["team", "stint"])["season"].transform("min")
    newbies = t[(t.season == first) & (t.season > t.season.min()) & (t.n < 10)]
    return {f"{s}_{n}": float(newbies[s].mean()) for n in bm.ROLL for s in bm.FORM_STATS}


def bookie_probs(df: pd.DataFrame) -> np.ndarray:
    """Implied probabilities with the bookmaker's margin removed (NaN where odds are missing)."""
    inv = 1 / df[["odds_h", "odds_d", "odds_a"]].to_numpy(float)
    return inv / inv.sum(1, keepdims=True)


def _models():
    return {
        "logistic": make_pipeline(StandardScaler(), LogisticRegression(C=0.05, max_iter=2000)),
        "xgboost": XGBClassifier(n_estimators=300, max_depth=2, learning_rate=0.03,
                                 subsample=0.8, colsample_bytree=0.7, min_child_weight=20,
                                 objective="multi:softprob", eval_metric="mlogloss"),
    }


def _fit(model, X, y):
    yi = y.map({c: i for i, c in enumerate(CLASSES)})
    model.fit(X, yi)
    return model


def _score(p: np.ndarray, y: pd.Series) -> dict:
    ok = ~np.isnan(p).any(axis=1)  # a few old games have no odds
    p, y = p[ok], y[ok]
    yi = y.map({c: i for i, c in enumerate(CLASSES)}).to_numpy()
    return {"log_loss": round(float(log_loss(yi, p, labels=[0, 1, 2])), 4),
            "accuracy": round(float(accuracy_score(yi, p.argmax(1))), 4), "n": int(len(y))}


def explain(model, X: pd.DataFrame) -> pd.DataFrame:
    """For each group: how much it shifts (P(home win) - P(away win)), in percentage points.
    Measured by resetting that group to 'evenly matched' and seeing what changes."""
    base = model.predict_proba(X)
    edge = base[:, 0] - base[:, 2]
    out = pd.DataFrame(index=X.index)
    for g, cols in GROUPS.items():
        Xn = X.copy()
        for c in cols:
            Xn[c] = NEUTRAL_REST if c.endswith("rest_days") else 0.0
        p = model.predict_proba(Xn)
        out[g] = np.round(100 * (edge - (p[:, 0] - p[:, 2])), 1)
    return out


def pairing_frame(state: pd.DataFrame, rest: dict | None = None) -> pd.DataFrame:
    """Feature rows for every ordered pair of clubs in the same league, using today's form."""
    s = state.set_index("team")
    rows = []
    for h in s.index:
        for a in s.index:
            if h == a or s.at[h, "league"] != s.at[a, "league"]:
                continue
            r = {"league": s.at[h, "league"], "home": h, "away": a,
                 "home_elo": s.at[h, "elo"], "away_elo": s.at[a, "elo"],
                 "h_rest_days": (rest or {}).get(h, NEUTRAL_REST),
                 "a_rest_days": (rest or {}).get(a, NEUTRAL_REST)}
            for c in FORM:
                r[f"h_{c}"], r[f"a_{c}"] = s.at[h, c], s.at[a, c]
            rows.append(r)
    return pd.DataFrame(rows)


def _report(frame: pd.DataFrame, p: np.ndarray) -> dict:
    """Model vs bookmakers, overall and per league."""
    out = {}
    for lg, idx in [("all", frame.index)] + list(frame.groupby("league").groups.items()):
        rows = frame.index.get_indexer(idx)
        sub = frame.loc[idx]
        out[lg] = {"model": _score(p[rows], sub.result), "bookmaker": _score(bookie_probs(sub), sub.result)}
    return out


def main():
    df, long, ratings = bm.build()
    done = df[df.season < CURRENT_SEASON]
    train_seasons = sorted(done.season.unique())[:-1]
    val_season = int(done.season.max())

    fill = promoted_prior(long, train_seasons)
    tr = done[done.season.isin(train_seasons)]
    va = done[done.season == val_season].reset_index(drop=True)
    Xtr, Xva = make_features(tr, fill), make_features(va, fill)

    report = {"validation_season": val_season,
              "bookmaker": _score(bookie_probs(va), va.result),
              "always_home_win": _score(np.tile([0.98, 0.01, 0.01], (len(va), 1)), va.result)}
    base_rate = tr.result.value_counts(normalize=True).reindex(CLASSES).to_numpy()
    report["base_rates"] = _score(np.tile(base_rate, (len(va), 1)), va.result)
    preds = {}
    for name, m in _models().items():
        _fit(m, Xtr, tr.result)
        preds[name] = m.predict_proba(Xva)
        report[name] = _score(preds[name], va.result)
    best = min(_models(), key=lambda k: report[k]["log_loss"])
    report["chosen"] = best
    report["by_league"] = _report(va, preds[best])
    print(json.dumps({k: v for k, v in report.items() if k != "by_league"}, indent=2))
    for lg, r in report["by_league"].items():
        print(f"  {lg:10} model {r['model']['log_loss']:.4f} / {r['model']['accuracy']:.1%}   "
              f"bookies {r['bookmaker']['log_loss']:.4f} / {r['bookmaker']['accuracy']:.1%}")

    # Production model: every completed season.
    fill = promoted_prior(long, sorted(done.season.unique()))
    model = _fit(_models()[best], make_features(done, fill), done.result)
    joblib.dump({"model": model, "fill": fill, "features": FEATURES, "name": best},
                MODELS / "match_model.joblib")

    # Track record: this season's finished matches, predicted out-of-sample.
    cur = df[df.season == CURRENT_SEASON].reset_index(drop=True)
    if len(cur):
        p = model.predict_proba(make_features(cur, fill))
        cur[["p_h", "p_d", "p_a"]] = p
        b = bookie_probs(cur)
        cur[["b_h", "b_d", "b_a"]] = b
        cur["pick"] = np.array(CLASSES)[p.argmax(1)]
        cur["bookie_pick"] = np.where(np.isnan(b).any(axis=1), None,
                                      np.array(CLASSES)[np.nan_to_num(b).argmax(1)])
        cur[["league", "date", "home", "away", "home_goals", "away_goals", "result", "p_h", "p_d", "p_a",
             "b_h", "b_d", "b_a", "pick", "bookie_pick"]].to_parquet(DATA / "track_record.parquet", index=False)
        report["current_season"] = _report(cur, p)

    # Every pairing of clubs in each league, from today's form (feeds the picker + simulator).
    fx = pd.read_parquet(DATA / "fixtures.parquet")
    teams = pd.read_parquet(DATA / "teams.parquet")
    state = bm.team_state_now(long, ratings, list(teams[["league", "team"]].itertuples(index=False)))
    missing_elo = state.elo.isna()
    if missing_elo.any():  # no top-flight history since 2016: start like a promoted side
        low = state.groupby("league")["elo"].transform(lambda e: e.nsmallest(3).mean())
        state.loc[missing_elo, "elo"] = low[missing_elo]
    for c in FORM:  # clubs with no recent top-flight form
        state[c] = state[c].fillna(fill[c])
    state.to_parquet(DATA / "team_state.parquet", index=False)
    pairs = pairing_frame(state)
    Xp = make_features(pairs, fill)
    pairs[["p_h", "p_d", "p_a"]] = model.predict_proba(Xp)
    pairs = pd.concat([pairs[["league", "home", "away", "p_h", "p_d", "p_a"]], explain(model, Xp)], axis=1)
    pairs.to_parquet(DATA / "pair_probs.parquet", index=False)

    # Upcoming fixtures, with rest = days since each club's previous scheduled league game
    # (same definition as in training).
    sched = pd.concat([fx[["fixture_id", "kickoff", "home"]].rename(columns={"home": "team"}),
                       fx[["fixture_id", "kickoff", "away"]].rename(columns={"away": "team"})])
    sched = sched.sort_values("kickoff")
    sched["rest"] = sched.groupby("team")["kickoff"].diff().dt.days.clip(upper=14).fillna(14)
    rest_of = sched.set_index(["fixture_id", "team"])["rest"]
    st = state.set_index("team")
    rows = []
    for f in fx[~fx.finished].itertuples():
        rest = {t: float(rest_of.get((f.fixture_id, t), NEUTRAL_REST)) for t in (f.home, f.away)}
        r = pairing_frame(st.loc[[f.home, f.away]].reset_index(), rest)
        rows.append(r[(r.home == f.home) & (r.away == f.away)].assign(
            fixture_id=f.fixture_id, gw=f.gw, kickoff=f.kickoff))
    upc = pd.concat(rows, ignore_index=True)
    Xu = make_features(upc, fill)
    upc[["p_h", "p_d", "p_a"]] = model.predict_proba(Xu)
    upc = pd.concat([upc[["league", "fixture_id", "gw", "kickoff", "home", "away", "p_h", "p_d", "p_a"]],
                     explain(model, Xu)], axis=1)
    upc.to_parquet(DATA / "upcoming.parquet", index=False)

    (DATA / "match_metrics.json").write_text(json.dumps(report, indent=2))
    print(f"chosen: {best} | pairs: {len(pairs)} | upcoming fixtures: {len(upc)}")


if __name__ == "__main__":
    main()
