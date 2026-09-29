"""One row per current Premier League player, joining FPL, Understat and Transfermarkt.

Stats cover a rolling "window" of last season + this season to date, so early-season
numbers aren't dominated by 4-5 games."""
import pandas as pd

from pipeline.config import CURRENT_SEASON, DATA
from pipeline.matching import match, match_by_dob
from pipeline.sources import fpl, transfermarkt, understat

PREV = CURRENT_SEASON - 1
FPL_STATS = ["minutes", "starts", "goals_scored", "assists", "clean_sheets", "goals_conceded",
             "saves", "bonus", "bps", "total_points", "expected_goals", "expected_assists",
             "expected_goals_conceded", "tackles", "clearances_blocks_interceptions",
             "recoveries", "defensive_contribution", "creativity", "threat", "influence",
             "yellow_cards", "red_cards"]
US_STATS = ["time", "shots", "key_passes", "npg", "npxG", "xA", "xGChain", "xGBuildup"]


def _with_understat(df: pd.DataFrame, season: int) -> pd.DataFrame:
    us = understat.players(season)
    m = match(df, us, "code", "understat_id", ["full", "web_name", "known_name"])
    us = us.set_index("understat_id")[US_STATS]
    out = df.merge(m[["code", "understat_id"]], on="code", how="left")
    return out.join(us, on="understat_id")


def team_games_played() -> pd.Series:
    fx = fpl.fixtures()
    done = fx[fx["finished"]]
    return pd.concat([done["home"], done["away"]]).value_counts()


def build() -> pd.DataFrame:
    cur = fpl.players()
    cur["full"] = cur["first_name"] + " " + cur["second_name"]
    cur = _with_understat(cur, CURRENT_SEASON)

    prev = fpl.past_season_players(PREV)
    prev["full"] = prev["first_name"] + " " + prev["second_name"]
    prev["known_name"] = None
    prev = _with_understat(prev, PREV)
    prev = prev.set_index("code")[FPL_STATS + US_STATS].add_prefix("prev_")

    df = cur[["code", "fpl_id", "full", "web_name", "team", "pos", "price", "form",
              "selected_by_percent", "status", "news", "chance_of_playing_next_round",
              "ep_next", "points_per_game", "birth_date", "understat_id", "known_name"]
             + FPL_STATS + US_STATS].rename(columns={"full": "name"})
    df = df.rename(columns={c: f"cur_{c}" for c in FPL_STATS + US_STATS})
    df = df.join(prev, on="code")
    df["in_pl_last_season"] = df["prev_minutes"].notna()
    df = df.copy()

    # Rolling window = last season + this season.
    for c in FPL_STATS + US_STATS:
        df[f"win_{c}"] = df[f"cur_{c}"].fillna(0) + df[f"prev_{c}"].fillna(0)
    gp = team_games_played()
    df["cur_team_games"] = df["team"].map(gp).fillna(0)
    df = df.copy()
    df["win_team_games"] = df["cur_team_games"] + df["in_pl_last_season"].map({True: 38, False: 0})
    df["win_minutes_share"] = (df["win_minutes"] / (df["win_team_games"].clip(lower=1) * 90)).clip(0, 1)

    today = pd.Timestamp.now().normalize()
    df["age"] = ((today - df["birth_date"]).dt.days / 365.25).round(1)

    # Transfermarkt profile + value (snapshot).
    tm = transfermarkt.players()
    link = match_by_dob(cur.assign(full=cur["first_name"] + " " + cur["second_name"]), tm,
                        "code", "tm_id", ["full", "web_name", "known_name"])
    tm = tm.rename(columns={"name": "tm_name"}).set_index("tm_id")[["tm_name", "sub_position", "position", "foot", "height_in_cm",
                                "international_caps", "contract_expiration_date",
                                "market_value_in_eur", "highest_market_value_in_eur"]]
    df = df.merge(link[["code", "tm_id"]], on="code", how="left").join(tm, on="tm_id")
    df = df.rename(columns={"market_value_in_eur": "tm_value", "position": "tm_position",
                            "highest_market_value_in_eur": "tm_peak_value"})
    # FPL uses full legal names ("Estêvão Almeida de Oliveira Gonçalves"); prefer the one fans use.
    known = df["known_name"].where(df["known_name"].fillna("").str.strip() != "")
    df["full_name"] = df["name"]
    df["name"] = known.fillna(df["tm_name"]).fillna(df["name"])
    df = df.drop(columns=["known_name"])
    df["contract_years_left"] = ((df["contract_expiration_date"] - today).dt.days / 365.25).round(1)
    return df


def main():
    df = build()
    df.to_parquet(DATA / "players.parquet", index=False)
    played = df[df["cur_minutes"] > 0]
    print(f"players: {len(df)} rows | played this season: {len(played)} | "
          f"understat linked: {played['understat_id'].notna().mean():.1%} | "
          f"transfermarkt linked: {played['tm_id'].notna().mean():.1%}")


if __name__ == "__main__":
    main()
