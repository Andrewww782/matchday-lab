"""Map club names from football-data.co.uk and Transfermarkt onto Understat's names.

Hand-maintaining ~100 clubs x 3 spellings is brittle ("Ath Madrid" / "Atletico Madrid" /
"Club Atlético de Madrid"), so both mappings are learned from the data itself:

- football-data.co.uk: the same match appears in both sources on the same day with the same
  score, so every match is a vote for "fd name X == Understat name Y".
- Transfermarkt: a club is whichever Understat squad shares the most players with it.

pipeline/club_overrides.csv (source,league,name,team) fixes anything the votes get wrong."""
from collections import Counter, defaultdict

import pandas as pd

from pipeline.config import CURRENT_SEASON, LEAGUES, MATCH_HISTORY_FROM, ROOT
from pipeline.matching import norm
from pipeline.sources import fdcouk, understat

OVERRIDES = ROOT / "pipeline" / "club_overrides.csv"


def _overrides(source: str) -> dict:
    if not OVERRIDES.exists():
        return {}
    ov = pd.read_csv(OVERRIDES)
    ov = ov[ov.source == source]
    return {(r.league, r["name"]): r.team for _, r in ov.iterrows()}


def learn_fd_names(league: str, fd: pd.DataFrame, us: pd.DataFrame) -> dict[str, str]:
    """fd/us: that league's matches across seasons (fd with home_raw/away_raw, us with home/away)."""
    votes: dict[str, Counter] = defaultdict(Counter)
    us = us.copy()
    for shift in (-1, 0, 1):  # kick-off dates can differ by a day between sources (time zones)
        u = us.assign(date=us["date"] + pd.Timedelta(days=shift))
        m = fd.merge(u, on=["season", "date", "home_goals", "away_goals"], suffixes=("", "_us"))
        for r in m.itertuples():
            w = 2 if shift == 0 else 1
            votes[r.home_raw][r.home] += w
            votes[r.away_raw][r.away] += w
    ov = _overrides("fdcouk")
    out = {}
    for name, c in votes.items():
        (best, n), *rest = c.most_common(2) + [("", 0)]
        runner = rest[0][1]
        if n >= 4 and n >= 3 * runner:
            out[name] = best
    for (lg, name), team in ov.items():
        if lg == league:
            out[name] = team
    return out


def fd_matches(league: str, seasons: range | None = None) -> pd.DataFrame:
    """football-data.co.uk matches for a league with club names mapped to Understat's."""
    seasons = seasons or range(MATCH_HISTORY_FROM, CURRENT_SEASON + 1)
    code = LEAGUES[league]["fdcouk"]
    fd = pd.concat([fdcouk.season(s, code) for s in seasons], ignore_index=True)
    us = pd.concat([understat.matches(s, league) for s in seasons], ignore_index=True)
    names = learn_fd_names(league, fd, us)
    fd["home"] = fd["home_raw"].map(names)
    fd["away"] = fd["away_raw"].map(names)
    fd["league"] = league
    missing = sorted(set(fd.loc[fd.home.isna(), "home_raw"]) | set(fd.loc[fd.away.isna(), "away_raw"]))
    if missing:
        print(f"  [{league}] football-data names not matched to Understat: {missing}")
    return fd


def _keys(name: str) -> set[str]:
    n = norm(name)
    parts = n.split()
    keys = {n}
    if len(parts) >= 2:
        keys.add(f"{parts[0][0]} {parts[-1]}")   # "b saka"
        keys.add(parts[-1])                     # "saka"
    return keys


def align_by_roster(left: pd.DataFrame, right: pd.DataFrame, club_col: str = "club",
                    min_shared: int = 3) -> dict[str, tuple[str, str]]:
    """left: players with [club_col, name]; right: players with [league, team, name].
    Returns {left club: (league, team)} for clubs whose squads clearly overlap."""
    index: dict[str, set] = defaultdict(set)
    for r in right[["league", "team", "name"]].dropna().itertuples():
        for k in _keys(r.name):
            index[k].add((r.league, r.team))
    ov = _overrides("transfermarkt")
    out = {}
    for club, g in left.dropna(subset=[club_col]).groupby(club_col):
        score: Counter = Counter()
        for name in g["name"].dropna():
            hits = set()
            for k in _keys(name):
                # Full names count fully; surname-only hits count a little (common surnames).
                w = 1.0 if " " in k and len(k) > 3 else 0.25
                for t in index.get(k, ()):
                    hits.add((t, w))
            best_per_team: dict = {}
            for t, w in hits:
                best_per_team[t] = max(best_per_team.get(t, 0), w)
            score.update(best_per_team)
        if not score:
            continue
        (team, s), *rest = score.most_common(2) + [(None, 0)]
        if s >= min_shared and s >= 2 * rest[0][1]:
            out[club] = team
    for (lg, name), team in ov.items():
        out[name] = (lg, team)
    return out
