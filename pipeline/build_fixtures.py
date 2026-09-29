"""This season's full schedule and club list for every league.

Premier League fixtures come from FPL (so gameweek numbers match the Fantasy game); other leagues
come from Understat, with a "matchday" number derived from each club's order of games."""
import json

import pandas as pd

from pipeline.config import CURRENT_SEASON, DATA, LEAGUES, ROOT
from pipeline.sources import fpl, understat

CLUBS_CSV = ROOT / "app" / "clubs.csv"


def _epl() -> pd.DataFrame:
    fx = fpl.fixtures().dropna(subset=["kickoff"])
    return pd.DataFrame({
        "league": "EPL", "fixture_id": "EPL:" + fx["id"].astype(str), "gw": fx["event"].astype("Int64"),
        "kickoff": fx["kickoff"], "home": fx["home"], "away": fx["away"],
        "home_goals": fx["team_h_score"], "away_goals": fx["team_a_score"], "finished": fx["finished"],
    })


def _derived_matchday(f: pd.DataFrame) -> pd.Series:
    """Round number from each club's running game count (postponed games slot in by date)."""
    long = pd.concat([f[["fixture_id", "kickoff", "home"]].rename(columns={"home": "team"}),
                      f[["fixture_id", "kickoff", "away"]].rename(columns={"away": "team"})])
    long = long.sort_values(["kickoff", "fixture_id"])
    long["n"] = long.groupby("team").cumcount() + 1
    return long.groupby("fixture_id")["n"].mean().round().astype("Int64")


def _understat(league: str) -> pd.DataFrame:
    u = understat.fixtures(CURRENT_SEASON, league)
    f = pd.DataFrame({
        "league": league, "fixture_id": league + ":" + u["understat_match_id"].astype(str),
        "kickoff": u["kickoff"], "home": u["home"], "away": u["away"],
        "home_goals": u["home_goals"], "away_goals": u["away_goals"], "finished": u["finished"],
    })
    f["gw"] = f["fixture_id"].map(_derived_matchday(f))
    return f


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    fx = pd.concat([_epl()] + [_understat(lg) for lg in LEAGUES if lg != "EPL"], ignore_index=True)
    fx["home_goals"] = pd.to_numeric(fx["home_goals"], errors="coerce")
    fx["away_goals"] = pd.to_numeric(fx["away_goals"], errors="coerce")
    fx["finished"] = fx["finished"].astype(bool)

    # Clubs: short code (FPL for England, Understat elsewhere) + colour from app/clubs.csv.
    short = {}
    for lg in LEAGUES:
        u = understat.fixtures(CURRENT_SEASON, lg)
        short.update(dict(zip(u["home"], u["home_short"])))
    short.update(fpl.teams().set_index("team")["short_name"].to_dict())
    teams = (pd.concat([fx[["league", "home"]].rename(columns={"home": "team"}),
                        fx[["league", "away"]].rename(columns={"away": "team"})])
             .drop_duplicates().sort_values(["league", "team"]).reset_index(drop=True))
    teams["short_name"] = teams["team"].map(short).fillna(teams["team"].str[:3].str.upper())
    colours = pd.read_csv(CLUBS_CSV) if CLUBS_CSV.exists() else pd.DataFrame(columns=["team", "colour"])
    teams["colour"] = teams["team"].map(colours.set_index("team")["colour"]).fillna("#888888")
    teams["league_name"] = teams["league"].map({k: v["name"] for k, v in LEAGUES.items()})
    return fx, teams


def main():
    fx, teams = build()
    fx.to_parquet(DATA / "fixtures.parquet", index=False)
    teams.to_parquet(DATA / "teams.parquet", index=False)
    # League rules for the app (it doesn't import pipeline code).
    (DATA / "leagues.json").write_text(json.dumps(
        {k: {f: v[f] for f in ("name", "clubs", "cl", "relegated", "playoff")} for k, v in LEAGUES.items()},
        indent=2))
    for lg, g in fx.groupby("league", sort=False):
        n = teams[teams.league == lg]
        print(f"  {lg:10} {len(g)} fixtures ({int(g.finished.sum())} played) | {len(n)} clubs "
              f"| no colour yet: {list(n.loc[n.colour == '#888888', 'team'])}")
    expected = pd.Series({k: v["clubs"] for k, v in LEAGUES.items()})
    if not teams.groupby("league").size().reindex(expected.index).equals(expected):
        raise ValueError("club count doesn't match the league registry")


if __name__ == "__main__":
    main()
