"""Player tables.

- build(): one row per current Premier League player, joining FPL, Understat and Transfermarkt
  (keyed by FPL `code`; feeds the Fantasy page via data/build/epl_players.parquet).
- build_all(): Europe's top 5 leagues, keyed by Understat id (feeds Value, Scout, Compare).

Stats cover a rolling "window" of last season + this season to date, so early-season
numbers aren't dominated by 4-5 games."""
import pandas as pd

from pipeline import clubs
from pipeline.config import BUILD, CURRENT_SEASON, DATA, LEAGUES
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


# ---------------------------------------------------------------------------------------------
# Europe's top 5 leagues: one row per player, keyed by Understat id (stable across leagues).

TM_POS = {"Goalkeeper": "GK", "Defender": "DEF", "Midfield": "MID", "Attack": "FWD"}
US_POS = {"G": "GK", "D": "DEF", "M": "MID", "F": "FWD"}
TM_COLS = ["tm_id", "tm_name", "sub_position", "tm_position", "foot", "height_in_cm",
           "international_caps", "contract_expiration_date", "tm_value", "tm_peak_value", "date_of_birth"]


def _tm_with_teams(us_rows: pd.DataFrame) -> pd.DataFrame:
    """Transfermarkt players with their club mapped to Understat's (league, team) by shared players."""
    tm = transfermarkt.players()
    link = clubs.align_by_roster(tm.rename(columns={"current_club_name": "club"}), us_rows)
    tm["league"] = tm["current_club_name"].map(lambda c: link.get(c, (None, None))[0])
    tm["team"] = tm["current_club_name"].map(lambda c: link.get(c, (None, None))[1])
    return tm.rename(columns={"name": "tm_name", "position": "tm_position",
                              "market_value_in_eur": "tm_value",
                              "highest_market_value_in_eur": "tm_peak_value"})


def build_all(epl: pd.DataFrame) -> pd.DataFrame:
    us = pd.concat([understat.players(s, lg) for s in (PREV, CURRENT_SEASON) for lg in LEAGUES],
                   ignore_index=True)
    us["understat_id"] = us["understat_id"].astype(int)

    # Where each player is now: his current-season row with the most minutes.
    cur = (us[us.season == CURRENT_SEASON].sort_values("time", ascending=False)
           .drop_duplicates("understat_id").set_index("understat_id"))
    win = us.groupby("understat_id")[US_STATS].sum()
    prev_league = (us[us.season == PREV].sort_values("time", ascending=False)
                   .drop_duplicates("understat_id").set_index("understat_id")["league"])

    # Premier League players keep their FPL-based rows (they include squad players who haven't
    # played yet this season); everyone else comes from Understat.
    e = epl.dropna(subset=["understat_id"]).copy()
    e["pid"] = e["understat_id"].astype(int)
    e = e.drop_duplicates("pid")
    e["league"] = "EPL"
    e["win_minutes_fpl"] = e["win_minutes"]
    others = cur[(cur.league != "EPL") & ~cur.index.isin(e["pid"])]

    o = pd.DataFrame({"pid": others.index, "league": others["league"].to_numpy(),
                      "team": others["team"].to_numpy(), "name": others["name"].to_numpy(),
                      "us_position": others["position"].to_numpy()})
    o["web_name"] = o["name"]
    for c in US_STATS:
        o[f"cur_{c}"] = others[c].to_numpy()
        o[f"win_{c}"] = o["pid"].map(win[c])
    o["cur_minutes"] = o["cur_time"]
    o["win_minutes"] = o["win_time"]

    # Minutes share: games the player's clubs have played in the window.
    fx = pd.read_parquet(DATA / "fixtures.parquet")
    done = fx[fx["finished"]]
    gp = pd.concat([done["home"], done["away"]]).value_counts()
    season_games = {k: (v["clubs"] - 1) * 2 for k, v in LEAGUES.items()}
    o["cur_team_games"] = o["team"].map(gp).fillna(0)
    o["win_team_games"] = o["cur_team_games"] + o["pid"].map(prev_league).map(season_games).fillna(0)
    o["win_minutes_share"] = (o["win_minutes"] / (o["win_team_games"].clip(lower=1) * 90)).clip(0, 1)

    # Transfermarkt: English players are already linked by date of birth; others by name + club.
    tm = _tm_with_teams(us)
    link = match(o, tm, "pid", "tm_id", ["name"], right_name="tm_name", min_team=80, min_global=95)
    o = o.merge(link[["pid", "tm_id"]], on="pid", how="left").merge(
        tm[TM_COLS], on="tm_id", how="left")
    today = pd.Timestamp.now().normalize()
    o["birth_date"] = o["date_of_birth"]
    o["age"] = ((today - o["birth_date"]).dt.days / 365.25).round(1)
    o["contract_years_left"] = ((o["contract_expiration_date"] - today).dt.days / 365.25).round(1)
    o["pos"] = o["tm_position"].map(TM_POS).fillna(o["us_position"].str[0].map(US_POS)).fillna("MID")
    o["name"] = o["tm_name"].fillna(o["name"])
    o = o.drop(columns=["date_of_birth", "us_position"])

    df = pd.concat([e, o], ignore_index=True)
    df["league_name"] = df["league"].map({k: v["name"] for k, v in LEAGUES.items()})
    return df


def main():
    epl = build()
    epl.to_parquet(BUILD / "epl_players.parquet", index=False)
    played = epl[epl["cur_minutes"] > 0]
    print(f"EPL (FPL) players: {len(epl)} rows | played this season: {len(played)} | "
          f"understat linked: {played['understat_id'].notna().mean():.1%} | "
          f"transfermarkt linked: {played['tm_id'].notna().mean():.1%}")

    df = build_all(epl)
    df.to_parquet(DATA / "players.parquet", index=False)
    for lg, g in df.groupby("league", sort=False):
        regular = g[g["win_time"] >= 450]
        print(f"  {lg:10} {len(g)} players | ≥450 min: {len(regular)} | "
              f"transfermarkt linked: {regular['tm_id'].notna().mean():.1%} | "
              f"with age: {regular['age'].notna().mean():.1%}")


if __name__ == "__main__":
    main()
