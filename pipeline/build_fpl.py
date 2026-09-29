"""Expected FPL points per player for the next few gameweeks, broken down by source.

Transparent on purpose: each part (goals, assists, clean sheet, ...) is a simple rate x
minutes x fixture adjustment, so the app can show exactly why a player is recommended."""
import json

import numpy as np
import pandas as pd
from scipy.stats import poisson

from pipeline.config import BUILD, DATA
from pipeline.sources import fpl

HORIZON = 5
POS_KEY = {"GK": "GKP", "DEF": "DEF", "MID": "MID", "FWD": "FWD"}
DC_THRESHOLD = {"GK": np.inf, "DEF": 10, "MID": 12, "FWD": 12}
PEN_PER_GAME, PEN_CONVERT = 0.11, 0.78
COMPONENTS = ["appearance", "goals", "assists", "clean_sheet", "conceded", "saves",
              "defensive", "bonus", "cards"]


def fixture_goals(up: pd.DataFrame, state: pd.DataFrame) -> pd.DataFrame:
    """Expected goals for each side of each upcoming fixture (attack x defence x venue)."""
    s = state.set_index("team")
    lg_for = s["xgf_10"].mean()
    home_adv = 1.12
    att = s["xgf_10"] / lg_for
    dfn = s["xga_10"] / lg_for
    up = up.copy()
    up["lam_h"] = lg_for * home_adv * up.home.map(att) * up.away.map(dfn)
    up["lam_a"] = lg_for / home_adv * up.away.map(att) * up.home.map(dfn)
    return up


def _blend(cur, prev, cur_games, weight_games=6):
    """Mix this season's per-game rate with last season's; this season takes over as games pass."""
    w = cur_games / (cur_games + weight_games)
    return np.where(np.isnan(prev), cur, w * cur + (1 - w) * prev)


def player_rates(p: pd.DataFrame) -> pd.DataFrame:
    r = pd.DataFrame(index=p.index)
    g_cur = p["cur_team_games"].clip(lower=1)
    r["exp_min"] = _blend(p["cur_minutes"] / g_cur, p["prev_minutes"] / 38, p["cur_team_games"])
    avail = p["chance_of_playing_next_round"].fillna(100) / 100
    avail = np.where(p["status"].isin(["i", "s", "u", "n"]), 0.0, avail)
    r["exp_min"] = (r["exp_min"] * avail).clip(0, 90)
    wm = p["win_minutes"].clip(lower=1)
    wt = p["win_time"].clip(lower=1)
    r["npxg90"] = p["win_npxG"] / wt * 90
    r["xa90"] = p["win_xA"] / wt * 90
    r["saves90"] = p["win_saves"] / wm * 90
    r["dc90"] = p["win_defensive_contribution"] / wm * 90
    r["bonus90"] = p["win_bonus"] / wm * 90
    r["yc90"] = p["win_yellow_cards"] / wm * 90
    # Thin samples (< 3 full games) get shrunk toward zero rather than trusted.
    shrink = (p["win_minutes"] / (p["win_minutes"] + 270)).to_numpy()
    for c in ["npxg90", "xa90", "saves90", "dc90", "bonus90"]:
        r[c] = r[c].fillna(0) * shrink
    return r


def expected_points(p: pd.DataFrame, up: pd.DataFrame, scoring: dict) -> pd.DataFrame:
    team_xg = up.melt(value_vars=["lam_h", "lam_a"]).value.mean()
    rates = player_rates(p)
    rows = []
    for f in up.itertuples():
        for side, team, opp, lam_for, lam_against in (
                ("H", f.home, f.away, f.lam_h, f.lam_a), ("A", f.away, f.home, f.lam_a, f.lam_h)):
            idx = p.index[p.team == team]
            if not len(idx):
                continue
            q, r = p.loc[idx], rates.loc[idx]
            pos = q["pos"]
            k = pos.map(POS_KEY)
            share = r["exp_min"] / 90
            p60 = (r["exp_min"] / 75).clip(0, 1)
            atk = lam_for / team_xg
            pens = np.where(q["penalties_order"] == 1, PEN_PER_GAME * PEN_CONVERT * atk, 0) * share
            goals = (r["npxg90"] * atk * share + pens) * k.map(scoring["goals_scored"])
            assists = r["xa90"] * atk * share * scoring["assists"]
            cs_p = np.exp(-lam_against)
            clean = cs_p * p60 * k.map(scoring["clean_sheets"])
            conceded = -(lam_against / 2 - 0.25 * (1 - np.exp(-2 * lam_against))) * p60 * \
                -k.map(scoring["goals_conceded"])
            saves = r["saves90"] * (lam_against / team_xg) * share / 3 * scoring["saves"]
            dc_p = 1 - poisson.cdf(pos.map(DC_THRESHOLD) - 1, (r["dc90"] * share).clip(lower=1e-6))
            defensive = np.nan_to_num(dc_p) * k.map(scoring["defensive_contribution"])
            appear = np.where(r["exp_min"] > 0, p60 * scoring["long_play"] + (1 - p60) * scoring["short_play"], 0)
            appear = appear * (r["exp_min"] > 0).clip(0, 1) * np.minimum(1, r["exp_min"] / 30)
            bonus = r["bonus90"] * share * (0.8 + 0.2 * atk)  # more bonus when the team should score more
            cards = r["yc90"] * share * scoring["yellow_cards"]
            part = pd.DataFrame({
                "code": q["code"], "gw": f.gw, "fixture_id": f.fixture_id, "opp": opp, "venue": side,
                "appearance": appear, "goals": goals, "assists": assists, "clean_sheet": clean,
                "conceded": -conceded.abs(), "saves": saves, "defensive": defensive,
                "bonus": bonus, "cards": cards, "exp_min": r["exp_min"],
            })
            rows.append(part)
    xp = pd.concat(rows, ignore_index=True)
    xp[COMPONENTS] = xp[COMPONENTS].fillna(0).round(3)
    xp["xpts"] = xp[COMPONENTS].sum(axis=1).round(2)
    return xp


def main():
    p = pd.read_parquet(BUILD / "epl_players.parquet")  # FPL is Premier League only
    boot = pd.DataFrame(fpl.bootstrap()["elements"])[["code", "penalties_order"]]
    p = p.merge(boot, on="code", how="left")
    scoring = fpl.bootstrap()["game_config"]["scoring"]
    up = pd.read_parquet(DATA / "upcoming.parquet").query("league == 'EPL'")
    next_gw = int(up.gw.min())
    up = up[up.gw < next_gw + HORIZON]
    up = fixture_goals(up, pd.read_parquet(DATA / "team_state.parquet").query("league == 'EPL'"))
    xp = expected_points(p, up, scoring)
    xp.to_parquet(DATA / "fpl_xpts.parquet", index=False)

    summ = xp.groupby("code").agg(xpts_next=("xpts", lambda s: s[xp.loc[s.index, "gw"] == next_gw].sum()),
                                  xpts_5=("xpts", "sum")).reset_index()
    out = p[["code", "fpl_id", "name", "web_name", "team", "pos", "price", "selected_by_percent",
             "form", "status", "news", "ep_next", "cur_total_points"]].merge(summ, on="code", how="left")
    out[["xpts_next", "xpts_5"]] = out[["xpts_next", "xpts_5"]].fillna(0).round(2)
    out.to_parquet(DATA / "fpl_players.parquet", index=False)
    up[["gw", "home", "away", "lam_h", "lam_a", "p_h", "p_d", "p_a"]].to_parquet(DATA / "fpl_fixtures.parquet", index=False)
    (DATA / "fpl_meta.json").write_text(json.dumps({"next_gw": next_gw, "horizon": HORIZON}))
    corr = out[["xpts_next", "ep_next"]].corr().iloc[0, 1]
    print(f"FPL xPts for GW{next_gw}-{next_gw + HORIZON - 1}: {len(out)} players | "
          f"correlation with FPL's own ep_next: {corr:.2f}")
    print(out.sort_values("xpts_5", ascending=False)[["web_name", "team", "pos", "price", "xpts_next", "ep_next", "xpts_5"]].head(12).to_string())


if __name__ == "__main__":
    main()
