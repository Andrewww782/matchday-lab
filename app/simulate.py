"""Monte Carlo season simulator: play the rest of the season thousands of times."""
import numpy as np
import pandas as pd

WIN_MARGIN_EXTRA = 0.55  # winning margin ~ 1 + Poisson(0.55): roughly the PL's real spread
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
        hg, ag = int(f.team_h_score), int(f.team_a_score)
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
             locked: dict[int, str] | None = None, seed: int = 7) -> dict:
    """remaining: home, away, p_h, p_d, p_a (one row per fixture, index = fixture id).
    locked: {fixture_id: "H" | "D" | "A"} forces a result (the what-if mode)."""
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

    margin = (1 + rng.poisson(WIN_MARGIN_EXTRA, (n, F))).astype(np.float32)
    home_gd = np.where(outcome == 0, margin, np.where(outcome == 2, -margin, 0)).astype(np.float32)
    gd = table["GD"].to_numpy(np.float32) + home_gd @ H - home_gd @ A

    score = pts * 1000 + gd + rng.random((n, T), dtype=np.float32) * 0.1
    order = np.argsort(-score, axis=1)
    pos = np.empty_like(order)
    pos[np.arange(n)[:, None], order] = np.arange(T)
    dist = np.stack([(pos == k).mean(0) for k in range(T)], axis=1)  # team x position

    out = pd.DataFrame(index=teams)
    out["exp_pts"] = pts.mean(0).round(1)
    out["title"] = dist[:, 0]
    out["top4"] = dist[:, :4].sum(1)
    out["top5"] = dist[:, :5].sum(1)
    out["relegated"] = dist[:, -3:].sum(1)
    out["avg_pos"] = (dist * np.arange(1, T + 1)).sum(1)
    return {"summary": out.sort_values(["exp_pts", "title"], ascending=False),
            "positions": pd.DataFrame(dist, index=teams, columns=range(1, T + 1))}
