"""Turn the pipeline's parquet artifacts into the JSON the Vercel app reads.

Run from anywhere:
    .venv\\Scripts\\python web\\scripts\\export_data.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.simulate import current_table, simulate  # noqa: E402

DATA = ROOT / "data"
OUT = ROOT / "web" / "data"
NOT_FACTORS = {
    "league", "home", "away", "p_h", "p_d", "p_a", "fixture_id", "gw", "kickoff",
    "xg_h", "xg_a", "p_btts", "p_over25", "p_cs_h", "p_cs_a", "top_scores", "grid",
}
VALUE_FACTORS = [
    "Age", "Position", "Playing time", "Goal threat", "Creativity",
    "Build-up play", "Team quality", "League",
]


def num(v, nd=4):
    if v is None or v is pd.NA:
        return None
    try:
        if pd.isna(v):
            return None
    except TypeError:
        pass
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (int,)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return None
        return round(x, nd)
    return v


def iso(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    try:
        if pd.isna(v):
            return None
    except TypeError:
        pass
    ts = pd.Timestamp(v)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC").isoformat()


def scores(raw):
    out = []
    if not isinstance(raw, str):
        return out
    for part in raw.split("|"):
        if ":" not in part:
            continue
        s, p = part.split(":")
        out.append({"score": s.replace("-", "–"), "p": num(float(p), 4)})
    return out


def factors(row, columns):
    out = []
    for col in columns:
        v = num(row[col], 2)
        if v is None:
            continue
        out.append({"label": col, "v": v})
    return out


def match_row(row, columns, with_when=False):
    item = {
        "league": row["league"],
        "home": row["home"],
        "away": row["away"],
        "ph": num(row["p_h"]),
        "pd": num(row["p_d"]),
        "pa": num(row["p_a"]),
        "xgH": num(row["xg_h"], 2) if "xg_h" in row else None,
        "xgA": num(row["xg_a"], 2) if "xg_a" in row else None,
        "btts": num(row["p_btts"]) if "p_btts" in row else None,
        "over": num(row["p_over25"]) if "p_over25" in row else None,
        "csH": num(row["p_cs_h"]) if "p_cs_h" in row else None,
        "csA": num(row["p_cs_a"]) if "p_cs_a" in row else None,
        "scores": scores(row["top_scores"]) if "top_scores" in row else [],
        "factors": factors(row, columns),
    }
    if with_when:
        item["gw"] = num(row["gw"], 0)
        item["kickoff"] = iso(row["kickoff"])
        item["id"] = str(row["fixture_id"]) if "fixture_id" in row and pd.notna(row["fixture_id"]) else None
    return item


def dump(name, obj):
    path = OUT / name
    path.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"  {name:20} {path.stat().st_size / 1e6:.2f} MB")


def about():
    mm = json.loads((DATA / "match_metrics.json").read_text(encoding="utf-8"))
    vm = json.loads((DATA / "value_metrics.json").read_text(encoding="utf-8"))
    gm = json.loads((DATA / "goals_metrics.json").read_text(encoding="utf-8"))
    leagues = json.loads((DATA / "leagues.json").read_text(encoding="utf-8"))
    head = mm.get("headline", mm)
    by_m, by_v, by_g = head.get("by_league", {}), vm.get("by_league", {}), gm.get("by_league", {})
    rows = []
    for key, cfg in leagues.items():
        bm, bv, bg = by_m.get(key, {}), by_v.get(key, {}), by_g.get(key, {})
        rows.append({
            "league": cfg["name"],
            "results": f"{bm['model']['accuracy']:.0%} / {bm['bookmaker']['accuracy']:.0%}" if bm else "–",
            "over": f"{bg['over25_accuracy']:.0%} / {bg['over25_accuracy_bookmaker']:.0%}" if bg else "–",
            "score": f"{bg['top3_hit']:.0%}" if bg else "–",
            "value": f"{bv['median_pct_error']:.0f}%" if bv else "–",
            "defence": "Yes" if key == "EPL" else "No",
        })
    all_row = by_m.get("all") or {}
    snap = vm.get("snapshot_date")
    return {
        "rows": rows,
        "allModel": f"{all_row['model']['accuracy']:.0%}" if all_row else None,
        "allBook": f"{all_row['bookmaker']['accuracy']:.0%}" if all_row else None,
        "alwaysHome": f"{mm['always_home_win']['accuracy']:.0%}" if mm.get("always_home_win") else None,
        "snapshot": pd.Timestamp(snap).strftime("%d %B %Y") if snap else None,
    }


def season_tables(fixtures, teams, upcoming, leagues):
    out = {}
    for key, cfg in leagues.items():
        names = sorted(teams.loc[teams["league"] == key, "team"].tolist())
        fx = fixtures[fixtures["league"] == key]
        table = current_table(fx, names)
        rem = upcoming[upcoming["league"] == key].dropna(subset=["p_h", "p_d", "p_a"])
        rem = rem.set_index("fixture_id")
        rows = []
        simulated = False
        try:
            if len(rem) and "grid" in rem.columns and rem["grid"].notna().all():
                res = simulate(
                    table, rem, n=10_000, cl=cfg["cl"], relegated=cfg["relegated"], playoff=cfg["playoff"],
                )
                summary = res["summary"]
                simulated = True
                for team, s in summary.iterrows():
                    base = table.loc[team]
                    rows.append({
                        "team": team,
                        "pts": int(base["Pts"]),
                        "p": int(base["P"]),
                        "gd": int(base["GD"]),
                        "gf": int(base["GF"]),
                        "ga": int(base["GA"]),
                        "expPts": num(s["exp_pts"], 1),
                        "expGd": num(s["exp_gd"], 0),
                        "title": num(s["title"]),
                        "cl": num(s["cl"]),
                        "relegated": num(s["relegated"]),
                        "playoff": num(s["playoff"]) if "playoff" in s else None,
                    })
        except Exception as exc:  # a bad grid should not sink the whole export
            print(f"  simulate {key} skipped: {exc}")
            rows = []
        if not rows:
            ordered = table.sort_values(["Pts", "GD", "GF"], ascending=False)
            for team, base in ordered.iterrows():
                rows.append({**row_from(base, team), "expPts": None, "expGd": None,
                             "title": None, "cl": None, "relegated": None, "playoff": None})
        out[key] = {"simulated": simulated, "rows": rows}
        print(f"  table {key}: {len(rows)} clubs, simulated={simulated}")
    return out


def row_from(base, team):
    return {
        "team": team,
        "pts": int(base["Pts"]),
        "p": int(base["P"]),
        "gd": int(base["GD"]),
        "gf": int(base["GF"]),
        "ga": int(base["GA"]),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    leagues = json.loads((DATA / "leagues.json").read_text(encoding="utf-8"))
    meta = json.loads((DATA / "meta.json").read_text(encoding="utf-8"))
    scout_meta = json.loads((DATA / "scout_meta.json").read_text(encoding="utf-8"))
    teams = pd.read_parquet(DATA / "teams.parquet")
    fixtures = pd.read_parquet(DATA / "fixtures.parquet")
    upcoming = pd.read_parquet(DATA / "upcoming.parquet")
    pairs = pd.read_parquet(DATA / "pair_probs.parquet")
    incidents = pd.read_parquet(DATA / "incidents.parquet")
    var_matches = pd.read_parquet(DATA / "var_matches.parquet")
    highlights = pd.read_parquet(DATA / "highlights.parquet")
    players = pd.read_parquet(DATA / "players.parquet")
    values = pd.read_parquet(DATA / "values.parquet")
    scout = pd.read_parquet(DATA / "scout.parquet")
    state = pd.read_parquet(DATA / "team_state.parquet")

    factor_cols = [c for c in pairs.columns if c not in NOT_FACTORS]
    order = list(leagues)
    site = {
        "updatedAt": meta.get("updated_at"),
        "season": meta.get("season"),
        "order": order,
        "leagues": {
            k: {**cfg, "round": "Gameweek" if k == "EPL" else "Matchday"}
            for k, cfg in leagues.items()
        },
        "teams": [
            {
                "league": r.league,
                "team": r.team,
                "short": r.short_name,
                "colour": r.colour if isinstance(r.colour, str) else "#161616",
            }
            for r in teams.itertuples()
        ],
        "about": about(),
        "scoutMeta": {
            "labels": scout_meta["labels"],
            "styleStats": scout_meta["style_stats"],
            "attStats": scout_meta["att_stats"],
            "minMinutes": scout_meta.get("min_minutes"),
        },
    }
    dump("site.json", site)

    dump("fixtures.json", [
        {
            "league": r.league,
            "gw": num(r.gw, 0),
            "kickoff": iso(r.kickoff),
            "home": r.home,
            "away": r.away,
            "hg": num(r.home_goals, 0),
            "ag": num(r.away_goals, 0),
            "finished": bool(r.finished),
        }
        for r in fixtures.itertuples()
    ])

    up_cols = [c for c in upcoming.columns if c not in NOT_FACTORS]
    dump("upcoming.json", [match_row(r, up_cols, True) for _, r in upcoming.iterrows()])
    dump("pairs.json", [match_row(r, factor_cols, False) for _, r in pairs.iterrows()])

    dump("incidents.json", [
        {
            "id": r.incident_id,
            "eventId": str(r.event_id),
            "league": r.league,
            "gw": num(r.gw, 0),
            "kickoff": iso(r.kickoff),
            "home": r.home,
            "away": r.away,
            "score": None if pd.isna(r.score) else str(r.score),
            "minute": num(r.minute, 0),
            "seconds": num(r.seconds, 0),
            "kind": r.kind,
            "big": bool(r.big),
            "headline": r.headline,
            "player": None if pd.isna(r.player) else str(r.player),
            "against": None if pd.isna(r.against_team) else str(r.against_team),
            "benefit": None if pd.isna(r.benefit_team) else str(r.benefit_team),
            "given": None if pd.isna(r.given) else str(r.given),
        }
        for r in incidents.itertuples()
    ])
    dump("var_matches.json", [
        {
            "eventId": str(r.event_id),
            "league": r.league,
            "gw": num(r.gw, 0),
            "kickoff": iso(r.kickoff),
            "home": r.home,
            "away": r.away,
            "score": None if pd.isna(r.score) else str(r.score),
            "referee": None if pd.isna(r.referee) else str(r.referee),
        }
        for r in var_matches.itertuples()
    ])
    highs = {}
    for r in highlights.itertuples():
        if pd.notna(r.video_id):
            highs[str(r.event_id)] = {"videoId": str(r.video_id), "title": None if pd.isna(r.title) else str(r.title)}
    dump("highlights.json", highs)

    played = players[players["win_time"] > 0].copy()
    played["label"] = played["name"] + " · " + played["team"]
    dupes = played["label"].duplicated(keep=False)
    played.loc[dupes, "label"] = played.loc[dupes, "label"] + " (" + played.loc[dupes, "league_name"] + ")"
    played = played.sort_values("win_time", ascending=False)
    dump("players.json", [
        {
            "pid": int(r.pid),
            "name": r.name,
            "web": None if pd.isna(r.web_name) else str(r.web_name),
            "team": r.team,
            "league": r.league,
            "leagueName": r.league_name,
            "pos": r.pos,
            "sub": None if pd.isna(r.sub_position) else str(r.sub_position),
            "age": num(r.age, 0),
            "value": num(r.tm_value, 0),
            "minutes": num(r.win_minutes, 0),
            "npg": num(r.win_npg, 2),
            "xa": num(r.win_xA, 2),
            "label": r.label,
        }
        for r in played.itertuples()
    ])

    value_rows = []
    for rec in values.to_dict("records"):
        value_rows.append({
            "pid": int(rec["pid"]),
            "league": rec["league"],
            "est": num(rec["est_value"], 0),
            "market": num(rec["tm_value"], 0),
            "ratio": num(rec["value_ratio"], 3),
            "verdict": rec["verdict"],
            "factors": [
                {"label": col, "v": v}
                for col in VALUE_FACTORS
                if (v := num(rec.get(col), 2)) is not None
            ],
        })
    dump("values.json", value_rows)

    p90_cols = [c for c in scout.columns if c.startswith("p90_")]
    pct_cols = [c for c in scout.columns if c.startswith("pct_") and not c.startswith("pct_eu_")]
    eu_cols = [c for c in scout.columns if c.startswith("pct_eu_")]
    dump("scout.json", [
        {
            "pid": int(rec["pid"]),
            "name": rec["name"],
            "web": rec.get("web_name"),
            "team": rec["team"],
            "league": rec["league"],
            "leagueName": rec["league_name"],
            "pos": rec["pos"],
            "age": num(rec.get("age"), 0),
            "value": num(rec.get("tm_value"), 0),
            "style": rec.get("style"),
            "minutes": num(rec.get("win_minutes"), 0),
            "p90": {c[4:]: num(rec.get(c), 3) for c in p90_cols},
            "pct": {c[4:]: num(rec.get(c), 1) for c in pct_cols},
            "pctEu": {c[7:]: num(rec.get(c), 1) for c in eu_cols},
        }
        for rec in scout.to_dict("records")
    ])

    dump("state.json", [
        {
            "league": r.league,
            "team": r.team,
            "elo": num(r.elo, 0),
            "pts5": num(r.pts_5, 2),
            "xgf5": num(r.xgf_5, 2),
            "xga5": num(r.xga_5, 2),
        }
        for r in state.itertuples()
    ])

    print("simulating seasons…")
    dump("tables.json", season_tables(fixtures, teams, upcoming, leagues))
    print("done")


if __name__ == "__main__":
    main()
