"""Refresh everything the app reads. Run weekly: `python -m pipeline.run_all`."""
import json
import time

import pandas as pd

from pipeline import build_fpl, build_matches, build_players, build_scout, train_match, train_value
from pipeline.config import CURRENT_SEASON, DATA, season_label
from pipeline.sources import fpl

STEPS = [
    ("players", build_players.main),
    ("matches", build_matches.main),
    ("match model", train_match.main),
    ("value model", train_value.main),
    ("scouting", build_scout.main),
    ("fpl", build_fpl.main),
]


def snapshot_fixtures():
    fpl.fixtures().to_parquet(DATA / "fixtures.parquet", index=False)
    fpl.teams().to_parquet(DATA / "teams.parquet", index=False)


def main():
    t0 = time.time()
    for name, fn in [("fixtures", snapshot_fixtures)] + STEPS:
        print(f"\n== {name} ==")
        fn()
    ev = fpl.events()
    finished = ev[ev.finished]
    meta = {
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(timespec="minutes"),
        "season": season_label(CURRENT_SEASON),
        "last_finished_gw": int(finished.id.max()) if len(finished) else 0,
    }
    (DATA / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"\nDone in {time.time() - t0:.0f}s: {meta}")


if __name__ == "__main__":
    main()
