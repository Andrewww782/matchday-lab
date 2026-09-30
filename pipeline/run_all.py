"""Refresh everything the app reads. Run weekly: `python -m pipeline.run_all`.

If a source is down, the HTTP layer serves the last good copy and the run carries on; those
sources are listed under "stale_sources" in data/meta.json (the weekly workflow opens an issue).
If a source has never been fetched at all, the run fails and the live site keeps last week's data."""
import json
import time

import pandas as pd

from pipeline import (build_fixtures, build_fpl, build_highlights, build_incidents, build_matches,
                      build_players, build_scout, http, train_goals, train_match, train_value)
from pipeline.config import CURRENT_SEASON, DATA, LEAGUES, season_label
from pipeline.sources import fpl

STEPS = [
    ("fixtures + clubs", build_fixtures.main),
    ("matches", build_matches.main),
    ("players", build_players.main),
    ("match model", train_match.main),
    ("goals model", train_goals.main),
    ("value model", train_value.main),
    ("scouting", build_scout.main),
    ("fpl", build_fpl.main),                      # parked in the app, but kept fresh for later
    ("fan var: incidents", build_incidents.main),
    ("fan var: highlights", build_highlights.main),
]


def _league_of(source: str) -> str:
    for lg, cfg in LEAGUES.items():
        if lg in source or f"/{cfg['fdcouk']}.csv" in source:
            return cfg["name"]
    if "fantasy.premierleague" in source or source.startswith("understat:"):
        return LEAGUES["EPL"]["name"]
    return "other"


def main():
    t0 = time.time()
    for name, fn in STEPS:
        print(f"\n== {name} ==")
        fn()
    ev = fpl.events()
    finished = ev[ev.finished]
    fx = pd.read_parquet(DATA / "fixtures.parquet")
    meta = {
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="minutes"),
        "season": season_label(CURRENT_SEASON),
        "last_finished_gw": int(finished.id.max()) if len(finished) else 0,
        "games_played": {lg: int(g.finished.sum()) for lg, g in fx.groupby("league")},
        "stale_sources": sorted(http.STALE),
        "stale_leagues": sorted({_league_of(s) for s in http.STALE}),
    }
    (DATA / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\nDone in {time.time() - t0:.0f}s: {meta}")


if __name__ == "__main__":
    main()
