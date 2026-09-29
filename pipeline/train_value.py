"""Transfer value model: what a player's on-pitch numbers suggest he's worth.

Deliberately excludes his previous market value, so the gap between our estimate and
Transfermarkt's is meaningful ("his stats say he's under/over-priced")."""
import json

import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

from pipeline import clubs
from pipeline.config import BUILD, CURRENT_SEASON, DATA, LEAGUES, MODELS, VALUE_TRAIN_SEASONS
from pipeline.matching import match
from pipeline.sources import transfermarkt, understat

PER90 = ["npg", "npxG", "xA", "shots", "key_passes", "xGChain", "xGBuildup"]
ROLES = ["GK", "CB", "FB", "DM", "CM", "AM", "W", "CF"]
_ROLE_MAP = {
    "Goalkeeper": "GK", "Centre-Back": "CB", "Left-Back": "FB", "Right-Back": "FB",
    "Defensive Midfield": "DM", "Central Midfield": "CM", "Attacking Midfield": "AM",
    "Left Midfield": "W", "Right Midfield": "W", "Left Winger": "W", "Right Winger": "W",
    "Second Striker": "CF", "Centre-Forward": "CF",
}
# Same stats are worth different money in different leagues (EPL is the baseline).
LEAGUE_FEATS = [f"lg_{k}" for k in LEAGUES if k != "EPL"]
FEATURES = ["age", "age_sq", "minutes_share", "team_ppg"] + [f"{c}_p90" for c in PER90] + \
           [f"role_{r}" for r in ROLES] + LEAGUE_FEATS
GROUPS = {
    "Age": ["age", "age_sq"],
    "Position": [f"role_{r}" for r in ROLES],
    "Playing time": ["minutes_share"],
    "Goal threat": ["npg_p90", "npxG_p90", "shots_p90"],
    "Creativity": ["xA_p90", "key_passes_p90", "xGChain_p90"],
    "Build-up play": ["xGBuildup_p90"],
    "Team quality": ["team_ppg"],
    "League": LEAGUE_FEATS,
}
SEASON_GAMES = {k: (v["clubs"] - 1) * 2 for k, v in LEAGUES.items()}
MIN_MINUTES = 450


def role(sub_position) -> str:
    return _ROLE_MAP.get(sub_position, "CM")


def team_ppg(seasons: list[int]) -> pd.DataFrame:
    long = pd.read_parquet(BUILD / "team_matches.parquet")
    return (long[long.season.isin(seasons)].groupby(["season", "league", "team"])["pts"].mean()
            .rename("team_ppg").reset_index())


def featurize(df: pd.DataFrame, minutes_col: str, share_col: str) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    X["age"] = df["age"]
    X["age_sq"] = (df["age"] - 26) ** 2
    X["minutes_share"] = df[share_col].clip(0, 1)
    X["team_ppg"] = df["team_ppg"]
    mins = df[minutes_col].clip(lower=1)
    for c in PER90:
        X[f"{c}_p90"] = (df[c] / mins * 90).clip(upper=df[c].quantile(0.999) / 450 * 90 + 1)
    r = df["sub_position"].map(role)
    for k in ROLES:
        X[f"role_{k}"] = (r == k).astype(float)
    for f in LEAGUE_FEATS:
        X[f] = (df["league"] == f[3:]).astype(float)
    return X[FEATURES]


def training_rows() -> pd.DataFrame:
    tm = transfermarkt.players()
    vals = transfermarkt.valuations()
    ppg = team_ppg(VALUE_TRAIN_SEASONS)
    rows = []
    for s in VALUE_TRAIN_SEASONS:
        us = pd.concat([understat.players(s, lg) for lg in LEAGUES], ignore_index=True)
        end = pd.Timestamp(f"{s + 1}-07-15")
        v = vals[(vals.date >= pd.Timestamp(f"{s + 1}-01-01")) & (vals.date <= end)]
        v = v.sort_values("date").groupby("tm_id").tail(1)
        v = v.merge(tm[["tm_id", "name", "date_of_birth", "sub_position"]], on="tm_id")
        # Club at valuation time -> Understat (league, team), learned from shared players.
        club_map = clubs.align_by_roster(v.rename(columns={"current_club_name": "club"}), us)
        v["team"] = v["current_club_name"].map(lambda c: club_map.get(c, (None, None))[1])
        us = us[us.time >= MIN_MINUTES]
        link = match(us, v, "understat_id", "tm_id", ["name"], min_team=85, min_global=95)
        d = us.merge(link[["understat_id", "tm_id"]], on="understat_id").merge(
            v[["tm_id", "value", "date_of_birth", "sub_position"]], on="tm_id")
        d["age"] = (pd.Timestamp(f"{s + 1}-07-01") - d["date_of_birth"]).dt.days / 365.25
        d["minutes_share"] = d["time"] / (d["league"].map(SEASON_GAMES) * 90)
        d = d.merge(ppg[ppg.season == s][["league", "team", "team_ppg"]], on=["league", "team"], how="left")
        rows.append(d.assign(season=s))
    out = pd.concat(rows, ignore_index=True).dropna(subset=["age", "value", "team_ppg"])
    return out[out.value > 0]


def _ridge():
    return make_pipeline(StandardScaler(), Ridge(alpha=3.0))


def _xgb():
    return XGBRegressor(n_estimators=900, max_depth=4, learning_rate=0.03,
                        subsample=0.8, colsample_bytree=0.8, min_child_weight=5)


class LeagueRidge:
    """One Ridge per league: each league prices the same numbers differently."""

    def fit(self, X, y, leagues):
        self.models = {lg: _ridge().fit(X[leagues == lg], y[leagues == lg]) for lg in leagues.unique()}
        return self

    def predict(self, X, leagues):
        out = pd.Series(np.nan, index=X.index)
        for lg, m in self.models.items():
            idx = leagues == lg
            if idx.any():
                out[idx] = m.predict(X[idx])
        return out.to_numpy()


class Pooled:
    def __init__(self, model):
        self.model = model

    def fit(self, X, y, leagues):
        self.model.fit(X, y)
        return self

    def predict(self, X, leagues):
        return self.model.predict(X)


class Blend:
    """Average (in log-value space) of per-league Ridge and a pooled XGBoost. Best on validation:
    the per-league models keep each market's pricing, the pooled trees share patterns."""

    def fit(self, X, y, leagues):
        self.ridge = LeagueRidge().fit(X, y, leagues)
        self.xgb = Pooled(_xgb()).fit(X, y, leagues)
        return self

    def predict(self, X, leagues):
        return (self.ridge.predict(X, leagues) + self.xgb.predict(X, leagues)) / 2


def _models():
    return {"per_league_ridge": LeagueRidge(), "pooled_ridge": Pooled(_ridge()),
            "xgboost": Pooled(_xgb()), "blend": Blend()}


def _metrics(y_true_log, y_pred_log) -> dict:
    t, p = np.exp(y_true_log), np.exp(y_pred_log)
    return {"mae_eur_m": round(float(np.mean(np.abs(t - p)) / 1e6), 2),
            "median_pct_error": round(float(np.median(np.abs(p / t - 1)) * 100), 1),
            "within_50pct": round(float(np.mean(np.abs(p / t - 1) <= 0.5) * 100), 1),
            "n": int(len(t))}


def _shap(model, X: pd.DataFrame, leagues: pd.Series, background: pd.DataFrame) -> np.ndarray:
    """SHAP values in log-value space. A blend's SHAP values are the average of its parts'."""
    if isinstance(model, Blend):
        return (_shap(model.ridge, X, leagues, background) + _shap(model.xgb, X, leagues, background)) / 2
    if isinstance(model, Pooled) and isinstance(model.model, XGBRegressor):
        return shap.TreeExplainer(model.model).shap_values(X)
    if isinstance(model, Pooled):
        models = {lg: model.model for lg in leagues.unique()}
    else:
        models = model.models
    sv = np.zeros(X.shape)
    for lg, m in models.items():
        idx = (leagues == lg).to_numpy()
        if idx.any():
            bg = m[0].transform(background)
            masker = shap.maskers.Independent(bg, max_samples=len(bg))
            sv[idx] = shap.LinearExplainer(m[-1], masker).shap_values(m[0].transform(X[idx]))
    return sv


def contributions(model, X: pd.DataFrame, leagues: pd.Series, background: pd.DataFrame) -> pd.DataFrame:
    """Grouped contributions to log(value), turned into % effects vs the average player."""
    sv = pd.DataFrame(_shap(model, X, leagues, background), columns=FEATURES, index=X.index)
    out = pd.DataFrame(index=X.index)
    for g, cols in GROUPS.items():
        out[g] = np.round(100 * (np.exp(sv[cols].sum(axis=1)) - 1), 1)
    return out


def main():
    d = training_rows()
    X, y = featurize(d, "time", "minutes_share"), np.log(d["value"])
    last = max(VALUE_TRAIN_SEASONS)
    tr, va = d.season < last, d.season == last
    report = {"validation_season": last, "train_rows": int(tr.sum())}
    preds = {}
    lg = d["league"]
    for name, m in _models().items():
        m.fit(X[tr], y[tr], lg[tr])
        preds[name] = pd.Series(m.predict(X[va], lg[va]), index=X[va].index)
        report[name] = _metrics(y[va], preds[name])
    best = min(_models(), key=lambda k: report[k]["median_pct_error"])
    report["chosen"] = best
    report["by_league"] = {k: _metrics(y[va][g.index], preds[best][g.index])
                           for k, g in d[va].groupby("league")}
    model = _models()[best].fit(X, y, lg)
    joblib.dump({"model": model, "name": best, "features": FEATURES}, MODELS / "value_model.joblib")

    # Current players: last season + this season window.
    p = pd.read_parquet(DATA / "players.parquet")
    ppg_now = team_ppg([CURRENT_SEASON - 1, CURRENT_SEASON]).groupby(["league", "team"])["team_ppg"].mean()
    cur = p.rename(columns={f"win_{c}": c for c in PER90 + ["time"]})
    cur["team_ppg"] = [ppg_now.get((lg, t), np.nan) for lg, t in zip(cur["league"], cur["team"])]
    # Newly promoted clubs have no top-flight record yet: use the league's weakest clubs.
    low = ppg_now.groupby(level=0).apply(lambda x: x.nsmallest(3).mean())
    cur["team_ppg"] = cur["team_ppg"].fillna(cur["league"].map(low))
    cur = cur[(cur["time"] >= MIN_MINUTES) & cur["age"].notna() & cur["team_ppg"].notna()].copy()
    Xc = featurize(cur, "time", "win_minutes_share")
    raw = pd.Series(np.exp(model.predict(Xc, cur["league"])), index=cur.index)
    # The model is trained on end-of-season values; recentre on today's market (per league) so
    # that "fair price" means "in line with how the market prices players like him there".
    calib = (cur["tm_value"] / raw).groupby(cur["league"]).median()
    cur["est_value"] = raw * cur["league"].map(calib)
    cur["value_ratio"] = cur["est_value"] / cur["tm_value"]
    cur["verdict"] = pd.cut(cur["value_ratio"], [0, 0.75, 1.33, np.inf],
                            labels=["Pricey", "Fair price", "Bargain"]).astype(str)
    cur.loc[cur["tm_value"].isna(), "verdict"] = "No market value"
    expl = contributions(model, Xc, cur["league"], X.sample(min(500, len(X)), random_state=0))
    out = pd.concat([cur[["pid", "league", "est_value", "tm_value", "value_ratio", "verdict"]], expl], axis=1)
    out.to_parquet(DATA / "values.parquet", index=False)

    report["market_calibration"] = calib.round(3).to_dict()
    report["snapshot_date"] = str(transfermarkt.snapshot_date().date())
    report["estimated_players"] = int(len(out))
    (DATA / "value_metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "by_league"}, indent=2))
    for lg, m in report["by_league"].items():
        print(f"  {lg:10} median error {m['median_pct_error']:.1f}% | within 50%: {m['within_50pct']:.0f}% | n={m['n']}")


if __name__ == "__main__":
    main()
