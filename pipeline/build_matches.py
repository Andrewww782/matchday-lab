"""Historical match table with pre-kickoff features (Elo + rolling form).

Every feature for a match is computed only from matches played *before* it."""
import numpy as np
import pandas as pd

from pipeline import clubs
from pipeline.config import BUILD, CURRENT_SEASON, LEAGUES, MATCH_HISTORY_FROM
from pipeline.sources import understat

ELO_START = 1500.0
ELO_K = 20.0
ELO_HOME = 60.0
ELO_CARRY = 0.8          # share of a rating kept over the summer (rest regresses to the mean)
ROLL = (5, 10)
FORM_STATS = ["gf", "ga", "xgf", "xga", "sf", "sa", "sotf", "sota", "pts"]


def load_league(league: str) -> pd.DataFrame:
    fd = clubs.fd_matches(league)
    us = pd.concat([understat.matches(s, league) for s in range(MATCH_HISTORY_FROM, CURRENT_SEASON + 1)])
    us = us[["season", "home", "away", "home_xg", "away_xg"]]
    return fd.merge(us, on=["season", "home", "away"], how="left")  # a pairing is unique per season


def load_matches(leagues=None) -> pd.DataFrame:
    df = pd.concat([load_league(lg) for lg in (leagues or LEAGUES)], ignore_index=True)
    df = df.dropna(subset=["home", "away"])
    clash = df.groupby("home")["league"].nunique()
    if (clash > 1).any():  # club names double as keys, so they must be unique across leagues
        raise ValueError(f"club name used in two leagues: {list(clash[clash > 1].index)}")
    df = df.sort_values(["date", "league", "home"]).reset_index(drop=True)
    df["result"] = np.select([df.home_goals > df.away_goals, df.home_goals < df.away_goals],
                             ["H", "A"], "D")
    df["match_id"] = np.arange(len(df))
    return df


def _elo_expect(r_home: float, r_away: float) -> float:
    return 1 / (1 + 10 ** ((r_away - (r_home + ELO_HOME)) / 400))


def add_elo(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Pre-match Elo, one rating pool per league (league clubs never meet each other)."""
    parts, ratings = [], {}
    for _, g in df.groupby("league", sort=False):
        g, r = _elo_one_league(g)
        parts.append(g)
        ratings.update(r)
    return pd.concat(parts).sort_values(["date", "league", "home"]).reset_index(drop=True), ratings


def _elo_one_league(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Pre-match Elo for both sides. Promoted clubs start at the average of the clubs they replaced."""
    ratings: dict[str, float] = {}
    pre_h, pre_a = [], []
    season = None
    for row in df.itertuples():
        if row.season != season:
            if season is not None:
                prev_teams = set(df.loc[df.season == season, "home"])
                new_teams = set(df.loc[df.season == row.season, "home"])
                down = prev_teams - new_teams
                promoted_start = np.mean([ratings[t] for t in down]) if down else ELO_START - 100
                ratings = {t: ELO_START + ELO_CARRY * (r - ELO_START) for t, r in ratings.items()}
                for t in new_teams - prev_teams:
                    ratings[t] = ELO_START + ELO_CARRY * (promoted_start - ELO_START)
            else:
                for t in set(df.loc[df.season == row.season, "home"]):
                    ratings[t] = ELO_START
            season = row.season
        rh, ra = ratings[row.home], ratings[row.away]
        pre_h.append(rh)
        pre_a.append(ra)
        exp = _elo_expect(rh, ra)
        score = 1.0 if row.result == "H" else 0.5 if row.result == "D" else 0.0
        margin = abs(row.home_goals - row.away_goals)
        mult = 1.0 if margin <= 1 else (1.5 if margin == 2 else (11 + margin) / 8)
        delta = ELO_K * mult * (score - exp)
        ratings[row.home] = rh + delta
        ratings[row.away] = ra - delta
    df = df.copy()
    df["home_elo"], df["away_elo"] = pre_h, pre_a
    return df, ratings


def team_long(df: pd.DataFrame) -> pd.DataFrame:
    """One row per team per match, from that team's point of view."""
    def side(h: bool) -> pd.DataFrame:
        me, op = ("home", "away") if h else ("away", "home")
        return pd.DataFrame({
            "match_id": df.match_id, "date": df.date, "season": df.season, "league": df.league,
            "team": df[me], "opp": df[op], "is_home": h,
            "gf": df[f"{me}_goals"], "ga": df[f"{op}_goals"],
            "xgf": df[f"{me}_xg"], "xga": df[f"{op}_xg"],
            "sf": df[f"{me}_shots"], "sa": df[f"{op}_shots"],
            "sotf": df[f"{me}_sot"], "sota": df[f"{op}_sot"],
            "pts": np.select([df[f"{me}_goals"] > df[f"{op}_goals"],
                              df[f"{me}_goals"] == df[f"{op}_goals"]], [3, 1], 0),
        })
    return pd.concat([side(True), side(False)]).sort_values(["team", "date"]).reset_index(drop=True)


def add_form(long: pd.DataFrame) -> pd.DataFrame:
    """Rolling means over each team's previous N league matches (shifted: no peeking)."""
    long = long.copy()
    # A "stint" is an unbroken run of top-flight seasons; form doesn't carry over a gap.
    gap = long.groupby("team")["season"].diff().fillna(0) > 1
    long["stint"] = gap.groupby(long["team"]).cumsum()
    g = long.groupby(["team", "stint"], group_keys=False)
    for n in ROLL:
        for s in FORM_STATS:
            long[f"{s}_{n}"] = g[s].transform(lambda x: x.shift(1).rolling(n, min_periods=3).mean())
    long["rest_days"] = g["date"].transform(lambda x: x.diff().dt.days).clip(upper=14).fillna(14)
    return long


def team_state_now(long: pd.DataFrame, ratings: dict, teams: list[tuple[str, str]]) -> pd.DataFrame:
    """Each current (league, team)'s latest Elo and form (including its most recent match)."""
    rows = []
    for league, t in teams:
        g = long[long.team == t]
        g = g[g.stint == g.stint.max()] if len(g) else g
        # A club that's new to the league (or back after years away) keeps no stale form.
        if len(g) and g.season.max() < CURRENT_SEASON - 1:
            g = g.iloc[0:0]
        row = {"league": league, "team": t, "elo": ratings.get(t, np.nan),
               "last_match": g.date.max() if len(g) else pd.NaT}
        for n in ROLL:
            tail = g.tail(n)
            for s in FORM_STATS:
                row[f"{s}_{n}"] = tail[s].mean() if len(tail) >= 3 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def form_columns() -> list[str]:
    return [f"{s}_{n}" for n in ROLL for s in FORM_STATS]


def build() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = load_matches()
    df, ratings = add_elo(df)
    long = add_form(team_long(df))
    feats = form_columns() + ["rest_days"]
    h = long[long.is_home].set_index("match_id")[feats].add_prefix("h_")
    a = long[~long.is_home].set_index("match_id")[feats].add_prefix("a_")
    df = df.join(h, on="match_id").join(a, on="match_id")
    return df, long, ratings


def main():
    df, long, ratings = build()
    df.to_parquet(BUILD / "matches.parquet", index=False)
    long.to_parquet(BUILD / "team_matches.parquet", index=False)
    for lg, g in df.groupby("league"):
        print(f"  {lg:10} matches: {len(g)} ({g.season.min()}-{g.season.max()}) | xG coverage "
              f"{g.home_xg.notna().mean():.1%} | odds coverage {g.odds_h.notna().mean():.1%}")


if __name__ == "__main__":
    main()
