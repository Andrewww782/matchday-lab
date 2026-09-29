"""Goals model: expected goals per side, a full scoreline grid, and the odds fans ask about
(most likely score, both teams to score, over 2.5 goals, clean sheets).

Dixon-Coles style, fitted per league:
  log(goals) = base + home advantage + attack(team) + defence weakness(opponent)
fitted as a weighted Poisson regression on a blend of goals and xG (xG is less noisy), with
recent games weighted more. A low-score correction (rho) fixes how often 0-0/1-0/0-1/1-1 happen.

The headline win/draw/loss is the average of the form model (train_match) and this model, which
beat either alone in every league on 2025/26. The grid is rescaled to match it, so the score
predictions always agree with the win % on the page."""
import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.stats import poisson
from sklearn.linear_model import PoissonRegressor

from pipeline.config import BUILD, CURRENT_SEASON, DATA, LEAGUES
from pipeline.train_match import GROUPS as FORM_GROUPS

MAX_GOALS = 10     # grid is 0..10 per side before truncation
GRID_KEEP = 10     # 0..9 per side stored for the app / simulator (>99.9% even for Bayern at home)
WINDOW_DAYS = 3 * 365
CALIBRATION_GAMES = 200  # recent games used to set the overall scoring level
EPS = 1e-12


# ----------------------------------------------------------------------------- fitting

class GoalsModel:
    def __init__(self, base, home, attack, defence, rho):
        self.base, self.home, self.attack, self.defence, self.rho = base, home, attack, defence, rho

    def rates(self, home: str, away: str) -> tuple[float, float]:
        a, d = self.attack, self.defence
        lh = np.exp(self.base + self.home + a.get(home, 0.0) + d.get(away, 0.0))
        la = np.exp(self.base + a.get(away, 0.0) + d.get(home, 0.0))
        return float(lh), float(la)


def _weights(dates: pd.Series, asof: pd.Timestamp, half_life: float) -> np.ndarray:
    age = (asof - dates).dt.days.to_numpy(float)
    return 0.5 ** (age / half_life)


def fit(m: pd.DataFrame, asof: pd.Timestamp, w_xg: float = 0.5, half_life: float = 240,
        alpha: float = 0.002) -> GoalsModel:
    """m: one league's matches. Only matches strictly before `asof` are used (no peeking)."""
    m = m[(m["date"] < asof) & (m["date"] >= asof - pd.Timedelta(days=WINDOW_DAYS))]
    m = m.dropna(subset=["home_goals", "away_goals"])
    hx = m["home_xg"].fillna(m["home_goals"])
    ax = m["away_xg"].fillna(m["away_goals"])
    y = np.concatenate([(1 - w_xg) * m["home_goals"] + w_xg * hx, (1 - w_xg) * m["away_goals"] + w_xg * ax])
    att = np.concatenate([m["home"], m["away"]])
    dfn = np.concatenate([m["away"], m["home"]])
    home = np.concatenate([np.ones(len(m)), np.zeros(len(m))])
    w = np.tile(_weights(m["date"], asof, half_life), 2)

    teams = sorted(set(att) | set(dfn))
    ti = {t: i for i, t in enumerate(teams)}
    T = len(teams)
    X = np.zeros((len(y), 2 * T + 1))
    X[np.arange(len(y)), [ti[t] for t in att]] = 1
    X[np.arange(len(y)), [T + ti[t] for t in dfn]] = 1
    X[:, -1] = home
    reg = PoissonRegressor(alpha=alpha, max_iter=1000).fit(X, y, sample_weight=w)
    coef = reg.coef_
    model = GoalsModel(reg.intercept_, coef[-1], {t: coef[ti[t]] for t in teams},
                       {t: coef[T + ti[t]] for t in teams}, 0.0)
    # Team strengths come from goals+xG, but the overall scoring level should match real goals:
    # rescale so the league's last ~200 games would have produced the goals they actually did.
    recent = m.tail(CALIBRATION_GAMES)
    pred = sum(sum(model.rates(h, a)) for h, a in zip(recent["home"], recent["away"]))
    model.base += np.log((recent["home_goals"] + recent["away_goals"]).sum() / pred)
    model.rho = fit_rho(m, model, _weights(m["date"], asof, half_life))
    return model


def _tau(x, y, lh, la, rho):
    """Dixon-Coles low-score adjustment."""
    t = np.ones_like(lh)
    t = np.where((x == 0) & (y == 0), 1 - lh * la * rho, t)
    t = np.where((x == 0) & (y == 1), 1 + lh * rho, t)
    t = np.where((x == 1) & (y == 0), 1 + la * rho, t)
    t = np.where((x == 1) & (y == 1), 1 - rho, t)
    return t


def fit_rho(m: pd.DataFrame, model: GoalsModel, w: np.ndarray) -> float:
    r = np.array([model.rates(h, a) for h, a in zip(m["home"], m["away"])])
    x, y = m["home_goals"].to_numpy(int), m["away_goals"].to_numpy(int)

    def nll(rho):
        t = _tau(x, y, r[:, 0], r[:, 1], rho)
        return -np.sum(w * np.log(np.clip(t, EPS, None)))

    return float(minimize_scalar(nll, bounds=(-0.2, 0.2), method="bounded").x)


# ----------------------------------------------------------------------------- grids

def grid(lh: float, la: float, rho: float) -> np.ndarray:
    """P(home scores i, away scores j), i, j = 0..MAX_GOALS."""
    g = np.outer(poisson.pmf(np.arange(MAX_GOALS + 1), lh), poisson.pmf(np.arange(MAX_GOALS + 1), la))
    g[0, 0] *= 1 - lh * la * rho
    g[0, 1] *= 1 + lh * rho
    g[1, 0] *= 1 + la * rho
    g[1, 1] *= 1 - rho
    g = np.clip(g, 0, None)
    return g / g.sum()


_I, _J = np.meshgrid(np.arange(MAX_GOALS + 1), np.arange(MAX_GOALS + 1), indexing="ij")
_HOME, _DRAW, _AWAY = _I > _J, _I == _J, _I < _J


def wdl(g: np.ndarray) -> tuple[float, float, float]:
    return float(g[_HOME].sum()), float(g[_DRAW].sum()), float(g[_AWAY].sum())


def condition_on_wdl(g: np.ndarray, p_h: float, p_d: float, p_a: float) -> np.ndarray:
    """Rescale so the grid's win/draw/loss totals equal the match model's probabilities."""
    h, d, a = wdl(g)
    return g * np.where(_HOME, p_h / max(h, EPS), np.where(_DRAW, p_d / max(d, EPS), p_a / max(a, EPS)))


def summaries(g: np.ndarray) -> dict:
    flat = np.argsort(g, axis=None)[::-1][:5]
    top = [(int(i), int(j), float(g[i, j])) for i, j in zip(*np.unravel_index(flat, g.shape))]
    keep = g[:GRID_KEEP, :GRID_KEEP]
    return {
        "xg_h": float((g.sum(axis=1) * np.arange(MAX_GOALS + 1)).sum()),
        "xg_a": float((g.sum(axis=0) * np.arange(MAX_GOALS + 1)).sum()),
        "p_btts": float(g[1:, 1:].sum()),
        "p_over25": float(g[(_I + _J) >= 3].sum()),
        "p_cs_h": float(g[:, 0].sum()),   # home keeps a clean sheet = away scores 0
        "p_cs_a": float(g[0, :].sum()),
        "top_scores": "|".join(f"{i}-{j}:{p:.4f}" for i, j, p in top),
        # Not renormalised: in lopsided games (Bayern at home) 7+ goals is a real possibility, and
        # squeezing that into 0-6 would shift the win/draw/loss shown next to it.
        "grid": keep.round(6).ravel().tolist(),
    }


# ----------------------------------------------------------------------------- backtest

def _weekly_predictions(m: pd.DataFrame, target: pd.DataFrame, **kw) -> pd.DataFrame:
    """Predict `target` week by week, each week fitted only on matches before that week."""
    target = target.copy()
    target["week"] = target["date"].dt.to_period("W-MON").dt.start_time
    out = []
    for wk, g in target.groupby("week"):
        model = fit(m, wk, **kw)
        for idx, r in g.iterrows():
            lh, la = model.rates(r["home"], r["away"])
            out.append({"idx": idx, "lh": lh, "la": la, "rho": model.rho, "fitted_asof": wk})
    return pd.DataFrame(out).set_index("idx")


def _score_logloss(frame: pd.DataFrame) -> float:
    ll = []
    for r in frame.itertuples():
        g = grid(r.lh, r.la, r.rho)
        i, j = min(int(r.home_goals), MAX_GOALS), min(int(r.away_goals), MAX_GOALS)
        ll.append(-np.log(max(g[i, j], EPS)))
    return float(np.mean(ll))


def _binary_ll(p, y):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def backtest(matches: pd.DataFrame, season: int, params: dict) -> dict:
    """Weekly out-of-sample evaluation of one season, per league."""
    out = {}
    val_preds = pd.read_parquet(BUILD / "match_val_preds.parquet")
    for lg in LEAGUES:
        m = matches[matches["league"] == lg]
        tgt = m[m["season"] == season].dropna(subset=["home_goals"])
        pr = tgt.join(_weekly_predictions(m, tgt, **params))
        assert (pr["fitted_asof"] <= pr["date"]).all()  # never fitted on the week being predicted
        tot = pr["home_goals"] + pr["away_goals"]
        over = (tot >= 3).astype(float)
        btts = ((pr["home_goals"] > 0) & (pr["away_goals"] > 0)).astype(float)
        grids = [grid(r.lh, r.la, r.rho) for r in pr.itertuples()]
        s = pd.DataFrame([summaries(g) for g in grids], index=pr.index)
        # Baseline: league-average scoring rates from the training window.
        train = m[m["season"] < season].tail(760)
        base = pr.assign(lh=train["home_goals"].mean(), la=train["away_goals"].mean(), rho=0.0)
        train_over = float(((train["home_goals"] + train["away_goals"]) >= 3).mean())
        inv = 1 / pr[["odds_o25", "odds_u25"]].to_numpy(float)
        bk_over = inv[:, 0] / inv.sum(1)
        has_odds = ~np.isnan(bk_over)
        top3 = [any(f"{int(r.home_goals)}-{int(r.away_goals)}:" in part for part in ts.split("|")[:3])
                for r, ts in zip(pr.itertuples(), s["top_scores"])]
        # Win/draw/loss: goals model vs match model vs a 50/50 blend (same games).
        v = pr.merge(val_preds, on=["league", "date", "home", "away"], how="inner")
        gw = np.array([wdl(grid(r.lh, r.la, r.rho)) for r in v.itertuples()])
        lm = v[["p_h", "p_d", "p_a"]].to_numpy()
        yi = v["result"].map({"H": 0, "D": 1, "A": 2}).to_numpy()

        def mll(p):
            return float(-np.mean(np.log(np.clip(p[np.arange(len(yi)), yi], EPS, None))))

        out[lg] = {
            "n": int(len(pr)),
            "avg_goals_actual": round(float(tot.mean()), 3),
            "avg_goals_predicted": round(float((pr["lh"] + pr["la"]).mean()), 3),
            "score_logloss": round(_score_logloss(pr), 4),
            "score_logloss_baseline": round(_score_logloss(base), 4),
            "top3_hit": round(float(np.mean(top3)), 3),
            "over25_logloss": round(_binary_ll(s["p_over25"][has_odds], over[has_odds]), 4),
            "over25_logloss_bookmaker": round(_binary_ll(bk_over[has_odds], over[has_odds]), 4),
            # Fair baseline: the over-2.5 rate of previous seasons (not of the season being predicted).
            "over25_logloss_base_rate": round(_binary_ll(np.full(has_odds.sum(), train_over), over[has_odds]), 4),
            "over25_accuracy": round(float(((s["p_over25"] > 0.5) == (over == 1)).mean()), 3),
            "over25_accuracy_bookmaker": round(float(((bk_over[has_odds] > 0.5) == (over[has_odds] == 1)).mean()), 3),
            "btts_accuracy": round(float(((s["p_btts"] > 0.5) == (btts == 1)).mean()), 3),
            "btts_base_rate_accuracy": round(float(max(btts.mean(), 1 - btts.mean())), 3),
            "wdl_logloss_match_model": round(mll(lm), 4),
            "wdl_logloss_goals_model": round(mll(gw), 4),
            "wdl_logloss_blend": round(mll((lm + gw) / 2), 4),
            "wdl_accuracy_match_model": round(float((lm.argmax(1) == yi).mean()), 4),
            "wdl_accuracy_blend": round(float((((lm + gw) / 2).argmax(1) == yi).mean()), 4),
            "rho": round(float(pr["rho"].median()), 4),
        }
        b = _bookie(v)
        ok = ~np.isnan(b).any(axis=1)
        out[lg]["wdl_logloss_bookmaker"] = round(float(-np.mean(np.log(np.clip(b[ok][np.arange(ok.sum()), yi[ok]], EPS, None)))), 4)
        out[lg]["wdl_accuracy_bookmaker"] = round(float((b[ok].argmax(1) == yi[ok]).mean()), 4)
    return out


def _bookie(df: pd.DataFrame) -> np.ndarray:
    inv = 1 / df[["odds_h", "odds_d", "odds_a"]].to_numpy(float)
    return inv / inv.sum(1, keepdims=True)


def tune(matches: pd.DataFrame, season: int) -> dict:
    """Pick the xG blend and time decay on the validation season (score + over-2.5 log-loss)."""
    best, best_loss, grid_results = None, np.inf, []
    for w_xg in (0.0, 0.5, 0.8):
        for half_life in (120, 240, 480):
            params = {"w_xg": w_xg, "half_life": half_life}
            loss = []
            for lg in LEAGUES:
                m = matches[matches["league"] == lg]
                tgt = m[m["season"] == season].dropna(subset=["home_goals"])
                pr = tgt.join(_weekly_predictions(m, tgt, **params))
                loss.append(_score_logloss(pr))
            mean = float(np.mean(loss))
            grid_results.append({**params, "score_logloss": round(mean, 4)})
            if mean < best_loss:
                best, best_loss = params, mean
    return {"chosen": best, "grid": grid_results}


# ----------------------------------------------------------------------------- outputs

GOAL_COLS = ["xg_h", "xg_a", "p_btts", "p_over25", "p_cs_h", "p_cs_a", "top_scores", "grid"]
GOALS_WHY = "Attack & defence strength"


def _blend(p_form: np.ndarray, mdl: GoalsModel, home: str, away: str):
    """Headline win/draw/loss = average of the form model and the goals model (it beat either
    alone in every league on 2025/26). Also returns the goals model's contribution to the home
    side's edge, vs two evenly matched teams, for the "Why?" panel."""
    raw = grid(*mdl.rates(home, away), mdl.rho)
    gw = np.array(wdl(raw))
    even = np.array(wdl(grid(np.exp(mdl.base + mdl.home), np.exp(mdl.base), mdl.rho)))
    edge = 100 * 0.5 * ((gw[0] - gw[2]) - (even[0] - even[2]))
    return (p_form + gw) / 2, raw, edge


def _enrich(frame: pd.DataFrame, models: dict) -> pd.DataFrame:
    """frame: the form model's rows (data/build/*_form.parquet). Returns the app's final rows."""
    frame = frame.drop(columns=[c for c in GOAL_COLS + [GOALS_WHY] if c in frame.columns]).reset_index(drop=True)
    why = [g for g in FORM_GROUPS if g in frame.columns]
    rows, probs, edges = [], [], []
    for r in frame.itertuples():
        p, raw, edge = _blend(np.array([r.p_h, r.p_d, r.p_a]), models[r.league], r.home, r.away)
        rows.append(summaries(condition_on_wdl(raw, *p)))
        probs.append(p)
        edges.append(edge)
    out = frame.copy()
    out[["p_h", "p_d", "p_a"]] = np.array(probs)
    out[why] = (out[why] * 0.5).round(1)  # the form model is now half of the headline
    out[GOALS_WHY] = np.round(edges, 1)
    return pd.concat([out, pd.DataFrame(rows)], axis=1)


def _headline_metrics(report_by_league: dict, tr: pd.DataFrame) -> dict:
    by_league = {lg: {"model": {"accuracy": r["wdl_accuracy_blend"], "log_loss": r["wdl_logloss_blend"], "n": r["n"]},
                      "bookmaker": {"accuracy": r["wdl_accuracy_bookmaker"], "log_loss": r["wdl_logloss_bookmaker"]}}
                 for lg, r in report_by_league.items()}
    n = sum(v["model"]["n"] for v in by_league.values())
    by_league["all"] = {k: {"accuracy": round(sum(v[k]["accuracy"] * v["model"]["n"] for lg, v in by_league.items()) / n, 4)}
                        for k in ("model", "bookmaker")}
    current = {lg: {"model": {"accuracy": round(float((g["pick"] == g["result"]).mean()), 4), "n": int(len(g))},
                    "bookmaker": {"accuracy": round(float((g["bookie_pick"] == g["result"])[g["bookie_pick"].notna()].mean()), 4)}}
               for lg, g in tr.groupby("league")}
    return {"method": "average of the form model and the goals model", "by_league": by_league,
            "current_season": current}


def main():
    matches = pd.read_parquet(BUILD / "matches.parquet")
    val_season = CURRENT_SEASON - 1
    tuning = tune(matches, val_season)
    params = tuning["chosen"]
    print(f"goals model params: {params}")
    report = {"validation_season": val_season, "params": params, "tuning": tuning["grid"],
              "by_league": backtest(matches, val_season, params)}
    for lg, r in report["by_league"].items():
        print(f"  {lg:10} goals {r['avg_goals_predicted']:.2f} vs {r['avg_goals_actual']:.2f} | score LL "
              f"{r['score_logloss']:.3f} (baseline {r['score_logloss_baseline']:.3f}) | top-3 {r['top3_hit']:.0%} | "
              f"O2.5 LL {r['over25_logloss']:.3f} vs bookies {r['over25_logloss_bookmaker']:.3f} | "
              f"W/D/L LL form {r['wdl_logloss_match_model']:.4f} blend {r['wdl_logloss_blend']:.4f} "
              f"bookies {r['wdl_logloss_bookmaker']:.4f} | acc blend {r['wdl_accuracy_blend']:.1%} "
              f"bookies {r['wdl_accuracy_bookmaker']:.1%}")

    # Current models (fitted on everything up to today) for upcoming games and all pairings.
    today = pd.Timestamp.now().normalize() + pd.Timedelta(days=1)
    models = {lg: fit(matches[matches["league"] == lg], today, **params) for lg in LEAGUES}
    for name in ("upcoming", "pair_probs"):
        f = pd.read_parquet(BUILD / f"{name}_form.parquet")
        _enrich(f, models).to_parquet(DATA / f"{name}.parquet", index=False)

    # Track record: this season's games, each predicted by models fitted before its week.
    tr = pd.read_parquet(BUILD / "track_record_form.parquet")
    cur = matches[matches["season"] == CURRENT_SEASON].dropna(subset=["home_goals"])
    parts = []
    for lg in LEAGUES:
        c = cur[cur["league"] == lg]
        if len(c):
            parts.append(c.join(_weekly_predictions(matches[matches["league"] == lg], c, **params)))
    wk = pd.concat(parts)[["league", "date", "home", "away", "lh", "la", "rho", "odds_o25", "odds_u25"]]
    tr = tr.merge(wk, on=["league", "date", "home", "away"], how="left")
    extra = []
    for r in tr.itertuples():
        gw = np.array(wdl(grid(r.lh, r.la, r.rho)))
        p = (np.array([r.p_h, r.p_d, r.p_a]) + gw) / 2
        s = summaries(condition_on_wdl(grid(r.lh, r.la, r.rho), *p))
        top = s["top_scores"].split("|")
        inv = 1 / np.array([r.odds_o25, r.odds_u25], float)
        extra.append({"p_h": p[0], "p_d": p[1], "p_a": p[2], "pick": "HDA"[int(p.argmax())],
                      "likely_score": top[0].split(":")[0], "p_over25": s["p_over25"], "p_btts": s["p_btts"],
                      "top3_hit": any(f"{int(r.home_goals)}-{int(r.away_goals)}:" in t for t in top[:3]),
                      "bookie_over25": inv[0] / inv.sum()})
    tr = pd.concat([tr.drop(columns=["p_h", "p_d", "p_a", "pick", "lh", "la", "rho", "odds_o25", "odds_u25"]),
                    pd.DataFrame(extra)], axis=1)
    tr.to_parquet(DATA / "track_record.parquet", index=False)

    report["current_season"] = {}
    for lg, g in tr.groupby("league"):
        over = ((g["home_goals"] + g["away_goals"]) >= 3).astype(float)
        ok = g["bookie_over25"].notna()
        report["current_season"][lg] = {
            "n": int(len(g)), "top3_hit": round(float(g["top3_hit"].mean()), 3),
            "over25_accuracy": round(float(((g["p_over25"] > 0.5) == (over == 1)).mean()), 3),
            "over25_accuracy_bookmaker": round(float(((g.loc[ok, "bookie_over25"] > 0.5) == (over[ok] == 1)).mean()), 3),
        }
    (DATA / "goals_metrics.json").write_text(json.dumps(report, indent=2))

    # Headline accuracy (what the site shows) now refers to the blend.
    mm = json.loads((DATA / "match_metrics.json").read_text())
    mm["headline"] = _headline_metrics(report["by_league"], tr)
    (DATA / "match_metrics.json").write_text(json.dumps(mm, indent=2))
    print("goals: upcoming, pair_probs and track_record written (headline = form + goals blend)")


if __name__ == "__main__":
    main()
