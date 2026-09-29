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
from pipeline.config import CURRENT_SEASON, DATA, MODELS
from pipeline.sources import fpl

CLASSES = ["H", "D", "A"]
FORM = bm.form_columns()
FEATURES = ["elo_diff"] + [f"d_{c}" for c in FORM] + ["h_rest_days", "a_rest_days"]

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
    return X[FEATURES]


def promoted_prior(long: pd.DataFrame, seasons: list[int]) -> dict:
    """Typical form of a newly promoted club in its first 10 games (used when form is unknown)."""
    t = long[long.season.isin(seasons)].copy()
    t["n"] = t.groupby(["team", "stint"]).cumcount()
    first = t.groupby(["team", "stint"])["season"].transform("min")
    newbies = t[(t.season == first) & (t.season > t.season.min()) & (t.n < 10)]
    return {f"{s}_{n}": float(newbies[s].mean()) for n in bm.ROLL for s in bm.FORM_STATS}


def bookie_probs(df: pd.DataFrame) -> np.ndarray:
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
    """Feature rows for every ordered pair of current clubs, using today's form."""
    s = state.set_index("team")
    rows = []
    for h in s.index:
        for a in s.index:
            if h == a:
                continue
            r = {"home": h, "away": a, "home_elo": s.at[h, "elo"], "away_elo": s.at[a, "elo"],
                 "h_rest_days": (rest or {}).get(h, NEUTRAL_REST),
                 "a_rest_days": (rest or {}).get(a, NEUTRAL_REST)}
            for c in FORM:
                r[f"h_{c}"], r[f"a_{c}"] = s.at[h, c], s.at[a, c]
            rows.append(r)
    return pd.DataFrame(rows)


def main():
    df, long, ratings = bm.build()
    done = df[df.season < CURRENT_SEASON]
    train_seasons = sorted(done.season.unique())[:-1]
    val_season = int(done.season.max())

    fill = promoted_prior(long, train_seasons)
    tr, va = done[done.season.isin(train_seasons)], done[done.season == val_season]
    Xtr, Xva = make_features(tr, fill), make_features(va, fill)

    report = {"validation_season": val_season,
              "bookmaker": _score(bookie_probs(va), va.result),
              "always_home_win": _score(np.tile([0.98, 0.01, 0.01], (len(va), 1)), va.result)}
    base_rate = tr.result.value_counts(normalize=True).reindex(CLASSES).to_numpy()
    report["base_rates"] = _score(np.tile(base_rate, (len(va), 1)), va.result)
    for name, m in _models().items():
        _fit(m, Xtr, tr.result)
        report[name] = _score(m.predict_proba(Xva), va.result)
    best = min(_models(), key=lambda k: report[k]["log_loss"])
    report["chosen"] = best
    print(json.dumps(report, indent=2))

    # Production model: every completed season.
    fill = promoted_prior(long, sorted(done.season.unique()))
    model = _fit(_models()[best], make_features(done, fill), done.result)
    joblib.dump({"model": model, "fill": fill, "features": FEATURES, "name": best},
                MODELS / "match_model.joblib")

    # Track record: this season's finished matches, predicted out-of-sample.
    cur = df[df.season == CURRENT_SEASON].copy()
    if len(cur):
        p = model.predict_proba(make_features(cur, fill))
        cur[["p_h", "p_d", "p_a"]] = p
        cur[["b_h", "b_d", "b_a"]] = bookie_probs(cur)
        cur["pick"] = np.array(CLASSES)[p.argmax(1)]
        cur["bookie_pick"] = np.array(CLASSES)[cur[["b_h", "b_d", "b_a"]].to_numpy().argmax(1)]
        cur[["date", "home", "away", "home_goals", "away_goals", "result", "p_h", "p_d", "p_a",
             "b_h", "b_d", "b_a", "pick", "bookie_pick"]].to_parquet(DATA / "track_record.parquet", index=False)
        report["current_season"] = {"model": _score(p, cur.result),
                                    "bookmaker": _score(bookie_probs(cur), cur.result)}

    # Every pairing of current clubs, from today's form (feeds the picker + simulator).
    teams = fpl.teams()["team"].tolist()
    state = bm.team_state_now(long, ratings, teams)
    for c in FORM:  # clubs with no top-flight form yet
        state[c] = state[c].fillna(fill[c])
    state.to_parquet(DATA / "team_state.parquet", index=False)
    pairs = pairing_frame(state)
    Xp = make_features(pairs, fill)
    pairs[["p_h", "p_d", "p_a"]] = model.predict_proba(Xp)
    pairs = pd.concat([pairs[["home", "away", "p_h", "p_d", "p_a"]], explain(model, Xp)], axis=1)
    pairs.to_parquet(DATA / "pair_probs.parquet", index=False)

    # Upcoming fixtures, with rest = days since each club's previous scheduled league game
    # (same definition as in training).
    fx = fpl.fixtures().dropna(subset=["kickoff"])
    sched = pd.concat([fx[["id", "kickoff", "home"]].rename(columns={"home": "team"}),
                       fx[["id", "kickoff", "away"]].rename(columns={"away": "team"})])
    sched = sched.sort_values("kickoff")
    sched["rest"] = sched.groupby("team")["kickoff"].diff().dt.days.clip(upper=14).fillna(14)
    rest_of = sched.set_index(["id", "team"])["rest"]
    up = fx[~fx.finished].copy()
    rows = []
    for f in up.itertuples():
        rest = {t: float(rest_of.get((f.id, t), NEUTRAL_REST)) for t in (f.home, f.away)}
        r = pairing_frame(state[state.team.isin([f.home, f.away])], rest)
        rows.append(r[(r.home == f.home) & (r.away == f.away)].assign(
            fixture_id=f.id, gw=f.event, kickoff=f.kickoff))
    upc = pd.concat(rows, ignore_index=True)
    Xu = make_features(upc, fill)
    upc[["p_h", "p_d", "p_a"]] = model.predict_proba(Xu)
    upc = pd.concat([upc[["fixture_id", "gw", "kickoff", "home", "away", "p_h", "p_d", "p_a"]],
                     explain(model, Xu)], axis=1)
    upc.to_parquet(DATA / "upcoming.parquet", index=False)

    (DATA / "match_metrics.json").write_text(json.dumps(report, indent=2))
    print(f"chosen: {best} | pairs: {len(pairs)} | upcoming fixtures: {len(upc)}")


if __name__ == "__main__":
    main()
