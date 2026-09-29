"""Fuzzy player matching across sources (names are spelled differently everywhere)."""
import re
import unicodedata

import pandas as pd
from rapidfuzz import fuzz, process

from pipeline.config import ROOT

OVERRIDES = ROOT / "pipeline" / "match_overrides.csv"


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _score(a: str, b: str, **_) -> float:
    # token_set handles "Thiago" vs "Igor Thiago"; ratio breaks ties toward exact spellings.
    return 0.7 * fuzz.token_set_ratio(a, b) + 0.3 * fuzz.ratio(a, b)


def match(left: pd.DataFrame, right: pd.DataFrame, left_id: str, right_id: str,
          left_names: list[str], right_name: str = "name",
          min_team: float = 80, min_global: float = 93) -> pd.DataFrame:
    """Map left[left_id] -> right[right_id].

    First look among the right-hand players at the same club (reliable even for short
    names); fall back to a league-wide search with a stricter threshold (transfers).
    `left_names` are alternative name columns on the left (e.g. full name and web name).
    Each right-hand player is used at most once, best score first."""
    r = right[[right_id, right_name, "team"]].dropna(subset=[right_name]).copy()
    r["_n"] = r[right_name].map(norm)
    by_team = {t: g for t, g in r.groupby("team")}
    all_names = r["_n"].tolist()
    all_ids = r[right_id].tolist()

    cands = []
    for _, row in left.iterrows():
        names = {norm(row[c]) for c in left_names if pd.notna(row.get(c))}
        best = (0.0, None)
        g = by_team.get(row.get("team"))
        if g is not None:
            for n in names:
                hit = process.extractOne(n, g["_n"].tolist(), scorer=_score)
                if hit and hit[1] > best[0]:
                    best = (hit[1], g.iloc[hit[2]][right_id])
        if best[0] < min_team:
            best = (0.0, None)
            for n in names:
                hit = process.extractOne(n, all_names, scorer=_score)
                if hit and hit[1] >= min_global and hit[1] > best[0]:
                    best = (hit[1], all_ids[hit[2]])
        if best[1] is not None:
            cands.append((best[0], row[left_id], best[1]))

    used_l, used_r, out = set(), set(), []
    for score, lid, rid in sorted(cands, key=lambda x: -x[0]):
        if lid in used_l or rid in used_r:
            continue
        used_l.add(lid)
        used_r.add(rid)
        out.append({left_id: lid, right_id: rid, "match_score": round(score, 1)})
    res = pd.DataFrame(out, columns=[left_id, right_id, "match_score"])
    return _apply_overrides(res, left_id, right_id)


def _apply_overrides(res: pd.DataFrame, left_id: str, right_id: str) -> pd.DataFrame:
    """Hand-fixed pairs in match_overrides.csv (columns: left_col,left_val,right_col,right_val)."""
    if not OVERRIDES.exists():
        return res
    ov = pd.read_csv(OVERRIDES)
    ov = ov[(ov.left_col == left_id) & (ov.right_col == right_id)]
    for _, o in ov.iterrows():
        lv = type(res[left_id].iloc[0])(o.left_val) if len(res) else o.left_val
        rv = type(res[right_id].iloc[0])(o.right_val) if len(res) else o.right_val
        res = res[(res[left_id] != lv) & (res[right_id] != rv)]
        res = pd.concat([res, pd.DataFrame([{left_id: lv, right_id: rv, "match_score": 100.0}])])
    return res.reset_index(drop=True)


def match_by_dob(left: pd.DataFrame, right: pd.DataFrame, left_id: str, right_id: str,
                 left_names: list[str], right_name: str = "name", min_score: float = 60) -> pd.DataFrame:
    """Match players sharing a date of birth; the name only has to be roughly similar."""
    r = right.dropna(subset=["date_of_birth"])
    by_dob = {d: g for d, g in r.groupby("date_of_birth")}
    out = []
    for _, row in left.dropna(subset=["birth_date"]).iterrows():
        g = by_dob.get(row["birth_date"])
        if g is None:
            continue
        names = {norm(row[c]) for c in left_names if pd.notna(row.get(c))}
        best = (0.0, None)
        for n in names:
            hit = process.extractOne(n, g[right_name].map(norm).tolist(), scorer=_score)
            if hit and hit[1] > best[0]:
                best = (hit[1], g.iloc[hit[2]][right_id])
        if best[0] >= min_score:
            out.append({left_id: row[left_id], right_id: best[1], "match_score": round(best[0], 1)})
    res = pd.DataFrame(out, columns=[left_id, right_id, "match_score"])
    res = res.sort_values("match_score", ascending=False).drop_duplicates(right_id)
    return _apply_overrides(res, left_id, right_id)
