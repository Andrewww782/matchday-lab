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

from pipeline.config import CURRENT_SEASON, DATA, MODELS, VALUE_TRAIN_SEASONS
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
FEATURES = ["age", "age_sq", "minutes_share", "team_ppg"] + [f"{c}_p90" for c in PER90] + \
           [f"role_{r}" for r in ROLES]
GROUPS = {
    "Age": ["age", "age_sq"],
    "Position": [f"role_{r}" for r in ROLES],
    "Playing time": ["minutes_share"],
    "Goal threat": ["npg_p90", "npxG_p90", "shots_p90"],
    "Creativity": ["xA_p90", "key_passes_p90", "xGChain_p90"],
    "Build-up play": ["xGBuildup_p90"],
    "Team quality": ["team_ppg"],
}
MIN_MINUTES = 450


def role(sub_position) -> str:
    return _ROLE_MAP.get(sub_position, "CM")


def team_ppg(seasons: list[int]) -> pd.DataFrame:
    long = pd.read_parquet(DATA / "team_matches.parquet")
    return long[long.season.isin(seasons)].groupby(["season", "team"])["pts"].mean().rename("team_ppg").reset_index()


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
    return X[FEATURES]


def training_rows() -> pd.DataFrame:
    tm = transfermarkt.players()
    vals = transfermarkt.valuations()
    ppg = team_ppg(VALUE_TRAIN_SEASONS)
    rows = []
    for s in VALUE_TRAIN_SEASONS:
        us = understat.players(s)
        us = us[us.time >= MIN_MINUTES]
        end = pd.Timestamp(f"{s + 1}-07-15")
        v = vals[(vals.date >= pd.Timestamp(f"{s + 1}-01-01")) & (vals.date <= end)]
        v = v.sort_values("date").groupby("tm_id").tail(1)
        v = v.merge(tm[["tm_id", "name", "date_of_birth", "sub_position"]], on="tm_id")
        link = match(us, v, "understat_id", "tm_id", ["name"], min_team=85, min_global=95)
        d = us.merge(link[["understat_id", "tm_id"]], on="understat_id").merge(
            v[["tm_id", "value", "date_of_birth", "sub_position"]], on="tm_id")
        d["age"] = (pd.Timestamp(f"{s + 1}-07-01") - d["date_of_birth"]).dt.days / 365.25
        d["minutes_share"] = d["time"] / (38 * 90)
        d = d.merge(ppg[ppg.season == s][["team", "team_ppg"]], on="team", how="left")
        rows.append(d.assign(season=s))
    out = pd.concat(rows, ignore_index=True).dropna(subset=["age", "value", "team_ppg"])
    return out[out.value > 0]


def _models():
    return {
        "ridge": make_pipeline(StandardScaler(), Ridge(alpha=3.0)),
        "xgboost": XGBRegressor(n_estimators=600, max_depth=3, learning_rate=0.03,
                                subsample=0.8, colsample_bytree=0.8, min_child_weight=5),
    }


def _metrics(y_true_log, y_pred_log) -> dict:
    t, p = np.exp(y_true_log), np.exp(y_pred_log)
    return {"mae_eur_m": round(float(np.mean(np.abs(t - p)) / 1e6), 2),
            "median_pct_error": round(float(np.median(np.abs(p / t - 1)) * 100), 1),
            "within_50pct": round(float(np.mean(np.abs(p / t - 1) <= 0.5) * 100), 1),
            "n": int(len(t))}


def contributions(model, name: str, X: pd.DataFrame, background: pd.DataFrame) -> pd.DataFrame:
    """Grouped contributions to log(value), turned into % effects vs the average player."""
    if name == "xgboost":
        sv = shap.TreeExplainer(model).shap_values(X)
    else:
        bg = model[0].transform(background)
        masker = shap.maskers.Independent(bg, max_samples=len(bg))
        sv = shap.LinearExplainer(model[-1], masker).shap_values(model[0].transform(X))
    sv = pd.DataFrame(sv, columns=FEATURES, index=X.index)
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
    for name, m in _models().items():
        m.fit(X[tr], y[tr])
        report[name] = _metrics(y[va], m.predict(X[va]))
    best = min(_models(), key=lambda k: report[k]["median_pct_error"])
    report["chosen"] = best
    model = _models()[best].fit(X, y)
    joblib.dump({"model": model, "name": best, "features": FEATURES}, MODELS / "value_model.joblib")

    # Current players: last season + this season window.
    p = pd.read_parquet(DATA / "players.parquet")
    ppg_now = team_ppg([CURRENT_SEASON - 1, CURRENT_SEASON]).groupby("team")["team_ppg"].mean()
    cur = p.rename(columns={f"win_{c}": c for c in PER90 + ["time"]})
    cur["team_ppg"] = cur["team"].map(ppg_now)
    cur = cur[(cur["time"] >= MIN_MINUTES) & cur["age"].notna() & cur["team_ppg"].notna()].copy()
    Xc = featurize(cur, "time", "win_minutes_share")
    raw = np.exp(model.predict(Xc))
    # The model is trained on end-of-season values; recentre on today's market so that
    # "fair price" means "in line with how the market prices players like him".
    calib = float(np.nanmedian(cur["tm_value"] / raw))
    cur["est_value"] = raw * calib
    cur["value_ratio"] = cur["est_value"] / cur["tm_value"]
    cur["verdict"] = pd.cut(cur["value_ratio"], [0, 0.75, 1.33, np.inf],
                            labels=["Pricey", "Fair price", "Bargain"]).astype(str)
    cur.loc[cur["tm_value"].isna(), "verdict"] = "No market value"
    expl = contributions(model, best, Xc, X.sample(min(500, len(X)), random_state=0))
    out = pd.concat([cur[["code", "est_value", "tm_value", "value_ratio", "verdict"]], expl], axis=1)
    out.to_parquet(DATA / "values.parquet", index=False)

    report["market_calibration"] = round(calib, 3)
    report["snapshot_date"] = str(transfermarkt.snapshot_date().date())
    report["estimated_players"] = int(len(out))
    (DATA / "value_metrics.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
