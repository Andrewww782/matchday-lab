"""Fan VAR: every refereeing call worth arguing about, for every finished match this season.

From ESPN's commentary we pick out "atoms" (a penalty conceded, a red card, a VAR decision, an
overturned goal, a penalty scored or saved) and group atoms that happen within a few minutes of each
other in the same match into one incident: foul in the box + VAR check + penalty scored = one call.

Writes data/incidents.parquet (one row per call), data/var_matches.parquet (one row per match) and
data/lineups.parquet (who played, for the "flag a moment" form)."""
import re
from collections import Counter, defaultdict

import pandas as pd
from rapidfuzz import process

from pipeline.config import DATA
from pipeline.matching import norm
from pipeline.sources import espn

GROUP_SECONDS = 240          # atoms this close together belong to the same call
BIG_KINDS = {"goal_overturned", "var_penalty", "var_no_penalty", "var_red", "var_card_check",
             "red", "penalty", "goal_stands", "var_other"}
# What fans can say it should have been instead, per kind of call.
OPTIONS = {
    "goal_overturned": ["Goal", "No goal"], "goal_stands": ["Goal", "No goal"],
    "var_penalty": ["Penalty", "No penalty"], "var_no_penalty": ["Penalty", "No penalty"],
    "penalty": ["Penalty", "No penalty"],
    "red": ["Red card", "Yellow card", "No card"], "var_red": ["Red card", "Yellow card", "No card"],
    "var_card_check": ["Red card", "Yellow card", "No card"], "yellow": ["Red card", "Yellow card", "No card"],
    "var_other": ["Right call", "Wrong call"],
}
# The decision as given, in the same vocabulary as OPTIONS (so "Right call" == this).
GIVEN = {"goal_overturned": "No goal", "goal_stands": "Goal", "var_penalty": "Penalty",
         "var_no_penalty": "No penalty", "penalty": "Penalty", "red": "Red card", "var_red": "Red card",
         "var_card_check": "Yellow card", "yellow": "Yellow card", "var_other": "Right call"}
PRIORITY = ["goal_overturned", "var_penalty", "var_no_penalty", "var_red", "var_card_check", "var_other",
            "red", "penalty", "goal_stands", "yellow"]

P = "(?P<player>.+?)"
T = r"\((?P<team>[^()]+)\)"
RULES = [
    ("overturned", re.compile(rf"^GOAL OVERTURNED BY VAR: {P} {T} scores")),
    ("var", re.compile(r"VAR Decision: (?P<what>Card upgraded|Card downgraded|No card change|No Goal|Goal|"
                       r"No Penalty|Penalty|Other Decision Cancelled|Other)\b(?P<rest>.*)")),
    ("pen_conceded", re.compile(rf"^Penalty conceded by {P} {T} (?P<how>after a foul|with a handball)")),
    ("pen_drawn", re.compile(rf"^Penalty (?P<team>.+?)\. {P} draws a foul in the penalty area")),
    ("second_yellow", re.compile(rf"^Second yellow card to {P} {T}(?: for (?P<reason>[^.]+))?\.")),
    ("red", re.compile(rf"^{P} {T} is shown the red card(?: for (?P<reason>[^.]+))?\.")),
    ("yellow", re.compile(rf"^{P} {T} is shown the yellow card(?: for (?P<reason>[^.]+))?\.")),
    ("pen_scored", re.compile(rf"^Goal!.*?\. {P} {T} converts the penalty")),
    ("pen_saved", re.compile(rf"^Penalty saved\. {P} {T}")),
    ("pen_missed", re.compile(rf"^Penalty missed[.!].*?\. {P} {T}")),
    ("goal_var_ok", re.compile(r"(?:Goal!|Own Goal).*confirmed following VAR", re.I)),
]
CONTEXT_ONLY = {"pen_scored", "pen_saved", "pen_missed", "pen_drawn"}  # never an incident on their own


def _atoms(summary: dict) -> list[dict]:
    out = []
    for c in summary.get("commentary", []):
        text = (c.get("text") or "").strip()
        play = c.get("play") or {}
        for kind, rx in RULES:
            m = rx.search(text)
            if not m:
                continue
            g = m.groupdict()
            parts = [p.get("athlete", {}).get("displayName") for p in play.get("participants") or []]
            out.append({
                "atom": kind, "text": text, "seconds": float((c.get("time") or {}).get("value") or 0),
                "clock": (c.get("time") or {}).get("displayValue", ""), "seq": c.get("sequence", 0),
                "player": g.get("player") or (parts[0] if parts else None),
                "other_player": parts[1] if len(parts) > 1 else None,
                "team": (play.get("team") or {}).get("displayName") or g.get("team"),
                "paren_team": g.get("team"), "reason": g.get("reason"), "how": g.get("how"),
                "what": g.get("what"), "rest": (g.get("rest") or "").strip(" ."),
                "play_type": (play.get("type") or {}).get("text"),
            })
            break
    return sorted(out, key=lambda a: (a["seconds"], a["seq"]))


def _group(atoms: list[dict]) -> list[list[dict]]:
    """Yellow cards stand alone (unless VAR looks at them); everything else groups by time."""
    groups: list[list[dict]] = []
    for a in atoms:
        if a["atom"] == "yellow":
            groups.append([a])
            continue
        last = next((g for g in reversed(groups) if g[0]["atom"] != "yellow"), None)
        if last and a["seconds"] - last[-1]["seconds"] <= GROUP_SECONDS:
            last.append(a)
        else:
            groups.append([a])
    # A VAR card check belongs with the card it reviewed.
    merged: list[list[dict]] = []
    for g in groups:
        if (merged and merged[-1][0]["atom"] == "yellow" and g and g[0]["atom"] == "var"
                and "card" in (g[0]["what"] or "").lower() and g[0]["seconds"] - merged[-1][-1]["seconds"] <= GROUP_SECONDS
                and norm(g[0]["player"] or "") == norm(merged[-1][0]["player"] or "")):
            merged[-1].extend(g)
        else:
            merged.append(g)
    return [g for g in merged if not all(a["atom"] in CONTEXT_ONLY for a in g)]


def _kind(g: list[dict]) -> str:
    kinds = set()
    for a in g:
        w = (a["what"] or "").lower()
        if a["atom"] == "overturned" or (a["atom"] == "var" and w == "no goal"):
            kinds.add("goal_overturned")
        elif a["atom"] == "var" and w == "penalty":
            kinds.add("var_penalty")
        elif a["atom"] == "var" and w == "no penalty":
            kinds.add("var_no_penalty")
        elif a["atom"] == "var" and w == "card upgraded":
            kinds.add("var_red")
        elif a["atom"] == "var" and w in ("no card change", "card downgraded"):
            kinds.add("var_card_check")
        elif a["atom"] == "var" and w == "goal":
            kinds.add("goal_stands")
        elif a["atom"] == "var":
            kinds.add("var_other")
        elif a["atom"] in ("red", "second_yellow"):
            kinds.add("red")
        elif a["atom"] == "pen_conceded":
            kinds.add("penalty")
        elif a["atom"] == "goal_var_ok":
            kinds.add("goal_stands")
        elif a["atom"] == "yellow":
            kinds.add("yellow")
    return next(k for k in PRIORITY if k in kinds) if kinds else "var_other"


def _first(g, *atoms, field="player"):
    for a in g:
        if a["atom"] in atoms and a.get(field):
            return a[field]
    return None


def _describe(kind: str, g: list[dict], team_of) -> dict:
    """Plain-English headline, the team that benefited, and the team it went against."""
    pen_by, pen_team = _first(g, "pen_conceded"), team_of(_first(g, "pen_conceded", field="team"))
    fouled = _first(g, "pen_drawn")
    handball = any(a["atom"] == "pen_conceded" and a["how"] == "with a handball" for a in g)
    outcome = ("scored" if any(a["atom"] == "pen_scored" for a in g) else "saved" if any(a["atom"] == "pen_saved" for a in g)
               else "missed" if any(a["atom"] == "pen_missed" for a in g) else None)
    red = next((a for a in g if a["atom"] in ("red", "second_yellow")), None)
    if kind == "goal_overturned":
        who, team = _first(g, "overturned"), team_of(_first(g, "overturned", field="team"))
        head = f"{who}'s goal for {team} ruled out by VAR" if who else "Goal ruled out after a VAR review"
        return {"headline": head, "player": who, "for_team": None, "against_team": team}
    if kind in ("var_penalty", "penalty"):
        why = "for handball" if handball else (f"for a foul on {fouled}" if fouled else "for a foul")
        via = " after a VAR review" if kind == "var_penalty" else ""
        head = f"Penalty{via} {why}" + (f" by {pen_by}" if pen_by else "") + (f": {outcome}" if outcome else "")
        return {"headline": head, "player": pen_by, "for_team": None, "against_team": pen_team}
    if kind == "var_no_penalty":
        v = next((a for a in g if a["atom"] == "var"), {})
        denied = team_of(v.get("rest") or v.get("team"))  # "VAR Decision: No Penalty Arsenal." names who asked
        return {"headline": f"VAR says no penalty for {denied}" if denied else "VAR checks for a penalty: no penalty given",
                "player": fouled or pen_by, "for_team": None, "against_team": denied}
    if kind in ("red", "var_red"):
        a = red or next((x for x in g if x["atom"] == "var"), None)
        who = a["player"] if a and a["atom"] != "var" else _first(g, "var")
        team = team_of(a["team"]) if a else None
        reason = f" ({red['reason']})" if red is not None and red.get("reason") else ""
        if pen_by:  # the same moment gave a penalty too
            head = (f"Penalty and red card: {who}" + (f" fouls {fouled}" if fouled else "")
                    + (", card upgraded by VAR" if kind == "var_red" else "") + (f", penalty {outcome}" if outcome else ""))
            return {"headline": head, "player": who, "for_team": None, "against_team": team}
        if kind == "var_red":
            head = f"VAR upgrades {who}'s card to red{reason}"
        elif red is not None and red["atom"] == "second_yellow":
            head = f"Second yellow, off goes {who}{reason}"
        else:
            head = f"Straight red for {who}{reason}"
        return {"headline": head, "player": who, "for_team": None, "against_team": team}
    if kind == "var_card_check":
        y = next((a for a in g if a["atom"] == "yellow"), None)
        who = (y or {}).get("player")
        return {"headline": f"VAR checks {who}'s yellow card: no change" if who else "VAR checks a card: no change",
                "player": who, "for_team": None, "against_team": team_of((y or {}).get("team"))}
    if kind == "yellow":
        a = g[0]
        head = f"Yellow card for {a['player']}" + (f" ({a['reason']})" if a.get("reason") else "")
        return {"headline": head, "player": a["player"], "for_team": None, "against_team": team_of(a["team"])}
    if kind == "goal_stands":
        a = next((x for x in g if x["atom"] in ("goal_var_ok", "var") and x.get("team")), {})
        m = re.search(r"\(([^()]+)\)\s*$", (a.get("rest") or "")) if a.get("atom") == "var" else None
        who = m.group(1) if m else (re.search(r"\. ([^.()]+?) \(", a.get("text", "")) or [None, None])[1]
        return {"headline": f"{who}'s goal stands after a VAR check" if who else "Goal stands after a VAR check",
                "player": who, "for_team": team_of(a.get("team")), "against_team": None}
    return {"headline": "VAR decision", "player": None, "for_team": None, "against_team": None}


def learn_names(sb: pd.DataFrame, fx: pd.DataFrame) -> dict[str, str]:
    """ESPN club name -> our club name, voted by same-day same-score matches (like pipeline/clubs.py)."""
    votes: dict[str, Counter] = defaultdict(Counter)
    s = sb[sb.completed].assign(day=lambda d: d.kickoff.dt.tz_convert("UTC").dt.normalize())
    f = fx[fx.finished].assign(day=lambda d: pd.to_datetime(d.kickoff, utc=True).dt.normalize())
    for shift in (-1, 0, 1):
        m = s.merge(f.assign(day=f.day + pd.Timedelta(days=shift)), on=["day", "home_goals", "away_goals"])
        for r in m.itertuples():
            w = 2 if shift == 0 else 1
            votes[r.home_raw][r.home] += w
            votes[r.away_raw][r.away] += w
    out = {k: c.most_common(1)[0][0] for k, c in votes.items()}
    ours = sorted(set(fx.home) | set(fx.away))
    for name in set(sb.home_raw) | set(sb.away_raw):  # anyone left (e.g. no finished game yet): fuzzy
        if name not in out:
            hit = process.extractOne(norm(name), {o: norm(o) for o in ours})
            if hit and hit[1] >= 80:
                out[name] = hit[2]
    return out


def match_incidents(league: str, ev, summary: dict, names: dict, fixture: dict | None) -> list[dict]:
    lookup = {norm(k): v for k, v in names.items()}

    def team_of(t):
        if not t:
            return None
        if t in names:
            return names[t]
        hit = lookup.get(norm(t))
        if hit:
            return hit
        best = process.extractOne(norm(t), lookup.keys())
        return lookup[best[0]] if best and best[1] >= 80 else t

    home, away = names.get(ev.home_raw, ev.home_raw), names.get(ev.away_raw, ev.away_raw)
    rows = []
    for g in _group(_atoms(summary)):
        kind = _kind(g)
        d = _describe(kind, g, team_of)
        against = d["against_team"]
        if against is None and d["for_team"] in (home, away):
            against = away if d["for_team"] == home else home
        if against not in (home, away):
            against = None
        rows.append({
            "incident_id": f"{ev.event_id}-{int(g[0]['seconds'])}", "event_id": ev.event_id, "league": league,
            "gw": (fixture or {}).get("gw"), "kickoff": ev.kickoff, "home": home, "away": away,
            "score": f"{int(ev.home_goals)}–{int(ev.away_goals)}", "minute": g[0]["clock"],
            "seconds": g[0]["seconds"], "kind": kind, "big": kind in BIG_KINDS, "headline": d["headline"],
            "player": d["player"], "against_team": against,
            "benefit_team": (away if against == home else home if against == away else None),
            "given": GIVEN[kind], "options": "|".join(OPTIONS[kind]),
            "lines": "\n".join(dict.fromkeys(a["text"] for a in g)),
            "var": any(a["atom"] in ("var", "overturned") for a in g) or kind.startswith("var_"),
        })
    return rows


def _lineups(ev, summary: dict, names: dict) -> list[dict]:
    rows = []
    for side in summary.get("rosters", []):
        team = names.get(side.get("team", {}).get("displayName"), side.get("team", {}).get("displayName"))
        for p in side.get("roster", []):
            if p.get("starter") or p.get("subbedIn"):
                rows.append({"event_id": ev.event_id, "team": team, "player": p["athlete"]["displayName"],
                             "jersey": p.get("jersey"), "starter": bool(p.get("starter"))})
    return rows


def main():
    fx = pd.read_parquet(DATA / "fixtures.parquet")
    incidents, matches, lineups = [], [], []
    for league in espn.SLUGS:
        sb = espn.scoreboard(league)
        f = fx[fx.league == league]
        names = learn_names(sb, f)
        unmatched = sorted((set(sb.home_raw) | set(sb.away_raw)) - set(names))
        if unmatched:
            print(f"  [{league}] ESPN clubs not matched: {unmatched}")
        fmap = {(r.home, r.away): {"gw": int(r.gw) if pd.notna(r.gw) else None, "fixture_id": r.fixture_id}
                for r in f.itertuples()}
        done = sb[sb.completed]
        for ev in done.itertuples():
            s = espn.summary(league, ev.event_id, True)
            home, away = names.get(ev.home_raw, ev.home_raw), names.get(ev.away_raw, ev.away_raw)
            fixture = fmap.get((home, away))
            officials = s.get("gameInfo", {}).get("officials") or [{}]
            matches.append({"event_id": ev.event_id, "league": league, "gw": (fixture or {}).get("gw"),
                            "fixture_id": (fixture or {}).get("fixture_id"), "kickoff": ev.kickoff,
                            "home": home, "away": away, "score": f"{int(ev.home_goals)}–{int(ev.away_goals)}",
                            "referee": officials[0].get("displayName")})
            rows = match_incidents(league, ev, s, names, fixture)
            for r in rows:
                r["referee"] = matches[-1]["referee"]
            incidents += rows
            lineups += _lineups(ev, s, names)
        print(f"  [{league}] {len(done)} matches, {sum(r['league'] == league and r['big'] for r in incidents)} big calls")
    inc = pd.DataFrame(incidents)
    # Two calls can start in the same second (e.g. two yellows); keep ids unique and stable.
    dup = inc.groupby("incident_id").cumcount()
    inc.loc[dup > 0, "incident_id"] = inc["incident_id"] + "-" + dup.astype(str)
    inc["gw"] = inc["gw"].astype("Int64")
    inc.to_parquet(DATA / "incidents.parquet", index=False)
    m = pd.DataFrame(matches)
    m["gw"] = m["gw"].astype("Int64")
    m.to_parquet(DATA / "var_matches.parquet", index=False)
    pd.DataFrame(lineups).to_parquet(DATA / "lineups.parquet", index=False)
    print(f"  {len(inc)} calls ({int(inc.big.sum())} big) from {len(m)} matches")


if __name__ == "__main__":
    main()
