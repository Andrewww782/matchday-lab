"""Monte Carlo season simulator: play the rest of the season thousands of times."""
import numpy as np
import pandas as pd

GRID_N = 10  # score grids cover 0..9 goals per side (from the goals model)
_I, _J = np.divmod(np.arange(GRID_N * GRID_N), GRID_N)            # home goals, away goals per cell
_REGIONS = (_I > _J, _I == _J, _I < _J)                            # home win, draw, away win


def _draw_scores(grids: np.ndarray, outcome: np.ndarray, rng) -> tuple[np.ndarray, np.ndarray]:
    """Given each simulated result, draw a scoreline from that fixture's score chances for that
    result (a simulated 'home win' becomes 1-0, 2-1, 3-0... in realistic proportions)."""
    n, F = outcome.shape
    hg = np.zeros((n, F), np.int8)
    ag = np.zeros((n, F), np.int8)
    u = rng.random((n, F))
    for f in range(F):
        g = grids[f]
        for k, region in enumerate(_REGIONS):
            rows = outcome[:, f] == k
            if not rows.any():
                continue
            w = np.where(region, g, 0.0)
            cdf = np.cumsum(w) / w.sum()
            cell = np.minimum(np.searchsorted(cdf, u[rows, f]), len(cdf) - 1)
            hg[rows, f], ag[rows, f] = _I[cell], _J[cell]
    return hg, ag
STRENGTH_SD = 0.35       # how far a club's true level may differ from today's estimate (log-odds)


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def _with_strength_uncertainty(p_h, p_a, hi, ai, n, T, rng):
    """Nobody knows exactly how good each club is. In each simulated season, every club gets a
    random shift in strength that applies to all its remaining games (injuries, new signings,
    a manager change...). Without this, the table would be far too certain.

    Each fixture's (win, draw, loss) is written as an ordered-logit with strength gap d and
    draw width c: P(home) = s(d - c), P(away) = s(-d - c). Shifts move d; c stays put."""
    lh, la = np.log(p_h / (1 - p_h)), np.log(p_a / (1 - p_a))
    d, c = (lh - la) / 2, -(lh + la) / 2
    shock = rng.normal(0, STRENGTH_SD, (n, T)).astype(np.float32)
    dd = d + shock[:, hi] - shock[:, ai]
    return _sigmoid(dd - c).astype(np.float32), _sigmoid(-dd - c).astype(np.float32)


def current_table(fixtures: pd.DataFrame, teams: list[str]) -> pd.DataFrame:
    done = fixtures[fixtures["finished"]]
    t = pd.DataFrame(0, index=teams, columns=["P", "W", "D", "L", "GF", "GA", "Pts"])
    for f in done.itertuples():
        hg, ag = int(f.home_goals), int(f.away_goals)
        for team, gf, ga in ((f.home, hg, ag), (f.away, ag, hg)):
            t.loc[team, ["P", "GF", "GA"]] += [1, gf, ga]
            res = "W" if gf > ga else "D" if gf == ga else "L"
            t.loc[team, res] += 1
            t.loc[team, "Pts"] += {"W": 3, "D": 1, "L": 0}[res]
    t["GD"] = t["GF"] - t["GA"]
    t = t.sort_values(["Pts", "GD", "GF"], ascending=False)
    t.insert(0, "Pos", range(1, len(t) + 1))
    return t


def simulate(table: pd.DataFrame, remaining: pd.DataFrame, n: int = 10_000,
             locked: dict[str, str] | None = None, seed: int = 7,
             cl: int = 4, relegated: int = 3, playoff: int | None = None) -> dict:
    """remaining: home, away, p_h, p_d, p_a (one row per fixture, index = fixture id).
    locked: {fixture_id: "H" | "D" | "A"} forces a result (the what-if mode).
    cl / relegated / playoff: the league's Champions League places, relegation places and
    relegation play-off position (e.g. 16th in the Bundesliga)."""
    teams = list(table.index)
    ti = {t: i for i, t in enumerate(teams)}
    T, F = len(teams), len(remaining)
    rng = np.random.default_rng(seed)

    hi = remaining["home"].map(ti).to_numpy()
    ai = remaining["away"].map(ti).to_numpy()
    ph, pa = _with_strength_uncertainty(remaining["p_h"].to_numpy(float), remaining["p_a"].to_numpy(float),
                                        hi, ai, n, T, rng)
    for fid, res in (locked or {}).items():
        if fid in remaining.index:
            j = remaining.index.get_loc(fid)
            ph[:, j], pa[:, j] = {"H": (1, 0), "D": (0, 0), "A": (0, 1)}[res]
    u = rng.random((n, F), dtype=np.float32)
    outcome = np.where(u < ph, 0, np.where(u > 1 - pa, 2, 1)).astype(np.int8)  # 0 H, 1 D, 2 A

    H = np.zeros((F, T), np.float32)
    A = np.zeros((F, T), np.float32)
    H[np.arange(F), hi] = 1
    A[np.arange(F), ai] = 1
    home_pts = np.select([outcome == 0, outcome == 1], [3, 1], 0).astype(np.float32)
    away_pts = np.select([outcome == 2, outcome == 1], [3, 1], 0).astype(np.float32)
    pts = table["Pts"].to_numpy(np.float32) + home_pts @ H + away_pts @ A

    grids = np.stack(remaining["grid"].to_numpy()).astype(float) if F else np.zeros((0, GRID_N ** 2))
    hg, ag = _draw_scores(grids, outcome, rng)
    hg, ag = hg.astype(np.float32), ag.astype(np.float32)
    gf = table["GF"].to_numpy(np.float32) + hg @ H + ag @ A
    ga = table["GA"].to_numpy(np.float32) + ag @ H + hg @ A
    gd = gf - ga

    # Ranking: points, then goal difference, then goals scored, then a coin toss.
    score = pts * 1e6 + (gd + 500) * 1e3 + gf + rng.random((n, T), dtype=np.float32) * 0.5
    order = np.argsort(-score, axis=1)
    pos = np.empty_like(order)
    pos[np.arange(n)[:, None], order] = np.arange(T)
    dist = np.stack([(pos == k).mean(0) for k in range(T)], axis=1)  # team x position

    out = pd.DataFrame(index=teams)
    out["exp_pts"] = pts.mean(0).round(1)
    out["exp_gd"] = gd.mean(0).round(0)
    out["title"] = dist[:, 0]
    out["cl"] = dist[:, :cl].sum(1)
    out["relegated"] = dist[:, T - relegated:].sum(1)
    if playoff:
        out["playoff"] = dist[:, playoff - 1]
    out["avg_pos"] = (dist * np.arange(1, T + 1)).sum(1)
    return {"summary": out.sort_values(["exp_pts", "title"], ascending=False),
            "positions": pd.DataFrame(dist, index=teams, columns=range(1, T + 1))}
