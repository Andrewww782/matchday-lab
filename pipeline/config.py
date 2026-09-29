"""Shared paths, seasons and name maps for the data pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"          # gitignored download cache
DATA = ROOT / "data"                 # small artifacts the app reads
MODELS = ROOT / "models"
for p in (RAW, DATA, MODELS):
    p.mkdir(parents=True, exist_ok=True)

USER_AGENT = "Mozilla/5.0 (matchday-lab data pipeline; weekly refresh)"

# Season start years. 2026 == the 2026/27 season.
CURRENT_SEASON = 2026
MATCH_HISTORY_FROM = 2016            # first season used for the match model
VALUE_TRAIN_SEASONS = [2022, 2023, 2024, 2025]


def season_label(start_year: int) -> str:
    return f"{start_year}/{str(start_year + 1)[-2:]}"


# Every spelling of a club seen across FPL, football-data.co.uk, Understat and
# Transfermarkt, mapped to the short name fans use.
_TEAM_VARIANTS = {
    "Arsenal": ["Arsenal", "Arsenal FC"],
    "Aston Villa": ["Aston Villa"],
    "Bournemouth": ["Bournemouth", "AFC Bournemouth"],
    "Brentford": ["Brentford", "Brentford FC"],
    "Brighton": ["Brighton", "Brighton & Hove Albion", "Brighton and Hove Albion"],
    "Burnley": ["Burnley", "Burnley FC"],
    "Cardiff": ["Cardiff", "Cardiff City"],
    "Chelsea": ["Chelsea", "Chelsea FC"],
    "Coventry": ["Coventry", "Coventry City"],
    "Crystal Palace": ["Crystal Palace"],
    "Everton": ["Everton", "Everton FC"],
    "Fulham": ["Fulham", "Fulham FC"],
    "Huddersfield": ["Huddersfield", "Huddersfield Town"],
    "Hull": ["Hull", "Hull City"],
    "Ipswich": ["Ipswich", "Ipswich Town"],
    "Leeds": ["Leeds", "Leeds United"],
    "Leicester": ["Leicester", "Leicester City"],
    "Liverpool": ["Liverpool", "Liverpool FC"],
    "Luton": ["Luton", "Luton Town"],
    "Man City": ["Man City", "Manchester City"],
    "Man Utd": ["Man Utd", "Man United", "Manchester United"],
    "Middlesbrough": ["Middlesbrough", "Middlesbrough FC"],
    "Newcastle": ["Newcastle", "Newcastle United"],
    "Norwich": ["Norwich", "Norwich City"],
    "Nott'm Forest": ["Nott'm Forest", "Nottingham Forest"],
    "Sheffield Utd": ["Sheffield United", "Sheffield Utd"],
    "Southampton": ["Southampton", "Southampton FC"],
    "Spurs": ["Spurs", "Tottenham", "Tottenham Hotspur"],
    "Stoke": ["Stoke", "Stoke City"],
    "Sunderland": ["Sunderland", "Sunderland AFC"],
    "Swansea": ["Swansea", "Swansea City"],
    "Watford": ["Watford", "Watford FC"],
    "West Brom": ["West Brom", "West Bromwich Albion"],
    "West Ham": ["West Ham", "West Ham United"],
    "Wolves": ["Wolves", "Wolverhampton Wanderers"],
}
TEAM_MAP = {v.lower(): canon for canon, vs in _TEAM_VARIANTS.items() for v in vs}


def canon_team(name: str | None) -> str | None:
    """Canonical club name, or the input unchanged if it's a club we don't track."""
    if name is None:
        return None
    return TEAM_MAP.get(str(name).strip().lower(), str(name).strip())


POSITIONS = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}
