"""Per-90 style profiles, playing-style clusters and percentiles for Scout + Compare.

Two profiles: a full one (defensive stats + keepers) where FPL data exists (Premier League), and
an attacking/creative one from Understat that compares players across all five leagues."""
import json

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from pipeline.config import DATA

MIN_MINUTES = 600

# Stat -> (window column, minutes column, label fans understand)
STATS = {
    "goals": ("win_npg", "win_time", "Goals (non-penalty)"),
    "npxG": ("win_npxG", "win_time", "Expected goals"),
    "shots": ("win_shots", "win_time", "Shots"),
    "xA": ("win_xA", "win_time", "Expected assists"),
    "key_passes": ("win_key_passes", "win_time", "Key passes"),
    "xGChain": ("win_xGChain", "win_time", "Involvement in attacks"),
    "xGBuildup": ("win_xGBuildup", "win_time", "Build-up play"),
    "tackles": ("win_tackles", "win_minutes", "Tackles"),
    "cbi": ("win_clearances_blocks_interceptions", "win_minutes", "Clearances, blocks & interceptions"),
    "recoveries": ("win_recoveries", "win_minutes", "Ball recoveries"),
    "saves": ("win_saves", "win_minutes", "Saves"),
    "goals_prevented": (None, "win_minutes", "Goals prevented"),
}
# Which stats describe each position's style (GKs are judged on different things).
STYLE_STATS = {
    "GK": ["saves", "goals_prevented", "xGBuildup", "recoveries"],
    "DEF": ["tackles", "cbi", "recoveries", "xGBuildup", "xA", "key_passes", "npxG", "xGChain"],
    "MID": ["goals", "npxG", "shots", "xA", "key_passes", "xGChain", "xGBuildup", "tackles", "cbi", "recoveries"],
    "FWD": ["goals", "npxG", "shots", "xA", "key_passes", "xGChain", "xGBuildup", "tackles", "recoveries"],
}
N_CLUSTERS = {"GK": 2, "DEF": 4, "MID": 5, "FWD": 3}
US_BASED = {"goals", "npxG", "shots", "xA", "key_passes", "xGChain", "xGBuildup"}

# Cross-league profile: Understat stats only, so no keepers and no defensive actions.
ATT_STATS = {
    "DEF": ["xGBuildup", "xA", "key_passes", "npxG", "xGChain"],
    "MID": ["goals", "npxG", "shots", "xA", "key_passes", "xGChain", "xGBuildup"],
    "FWD": ["goals", "npxG", "shots", "xA", "key_passes", "xGChain", "xGBuildup"],
}
N_CLUSTERS_ATT = {"DEF": 3, "MID": 4, "FWD": 3}
# Without tackles/interceptions we can't say "ball winner"; low attacking involvement is the
# honest description.
ATT_RULES = [
    ("DEF", {"xA": 1, "key_passes": 1}, "Attacking full-back"),
    ("DEF", {"xGBuildup": 1}, "Ball-playing defender"),
    ("DEF", {"xGChain": -1, "xA": -1}, "Stay-at-home defender"),
    ("MID", {"goals": 1, "npxG": 1, "shots": 1}, "Goal-scoring midfielder"),
    ("MID", {"xA": 1, "key_passes": 1}, "Creator"),
    ("MID", {"xGBuildup": 1}, "Deep playmaker"),
    ("MID", {"xGChain": -1, "shots": -1}, "Holding midfielder"),
    ("FWD", {"npxG": 1, "xA": 1, "xGChain": 1}, "Complete forward"),
    ("FWD", {"goals": 1, "npxG": 1, "shots": 0.5}, "Poacher"),
    ("FWD", {"xA": 1, "key_passes": 1, "xGBuildup": 0.5}, "Creative forward"),
    ("FWD", {"npxG": -1, "shots": -1}, "Link-up forward"),
]

# Style names chosen by looking at each cluster's standout stats (see name_cluster).
STYLE_RULES = [
    ("GK", {"goals_prevented": 1, "saves": 1}, "Shot-stopper"),
    ("GK", {"xGBuildup": 1, "recoveries": 1}, "Sweeper keeper"),
    ("DEF", {"cbi": 1}, "Stopper"),
    ("DEF", {"tackles": 1, "recoveries": 0.5}, "Front-foot defender"),
    ("DEF", {"xGBuildup": 1}, "Ball-playing defender"),
    ("DEF", {"xA": 1, "key_passes": 1}, "Attacking full-back"),
    ("MID", {"goals": 1, "npxG": 1, "shots": 1}, "Goal-scoring midfielder"),
    ("MID", {"xA": 1, "key_passes": 1}, "Creator"),
    ("MID", {"xGBuildup": 1}, "Deep playmaker"),
    ("MID", {"tackles": 1, "cbi": 0.5, "recoveries": 1}, "Ball winner"),
    ("MID", {"xGChain": 0.5, "recoveries": 0.5}, "Box-to-box"),
    ("FWD", {"npxG": 1, "xA": 1, "xGChain": 1}, "Complete forward"),
    ("FWD", {"goals": 1, "npxG": 1, "shots": 0.5}, "Poacher"),
    ("FWD", {"xA": 1, "key_passes": 1, "xGBuildup": 0.5}, "Creative forward"),
    ("FWD", {"tackles": 1, "recoveries": 1}, "Pressing forward"),
]


def per90(df: pd.DataFrame) -> pd.DataFrame:
    """Per-90 numbers. Understat stats exist for every league; FPL-based ones (tackles, saves...)
    only for the Premier League, and stay NaN elsewhere rather than pretending to be zero."""
    out = pd.DataFrame(index=df.index)
    for k, (col, mins, _) in STATS.items():
        m = df[mins].clip(lower=1)
        if k == "goals_prevented":  # xG faced minus goals let in, per 90
            out[k] = (df["win_expected_goals_conceded"] - df["win_goals_conceded"]) / m * 90
        elif col.startswith("win_") and k in US_BASED:
            out[k] = df[col].fillna(0) / m * 90
        else:
            out[k] = df[col] / m * 90
    return out


def name_clusters(pos: str, centroids: pd.DataFrame, rules_table=None) -> dict[int, str]:
    """Give each cluster the best-fitting style name (each name used once)."""
    rules = [(w, n) for p, w, n in (rules_table or STYLE_RULES) if p == pos]
    scores = [(sum(centroids.loc[c].get(s, 0) * wt for s, wt in w.items()), c, n)
              for c in centroids.index for w, n in rules]
    names, used = {}, set()
    for _, c, n in sorted(scores, reverse=True):
        if c not in names and n not in used:
            names[c] = n
            used.add(n)
    for c in centroids.index:
        names.setdefault(c, "All-rounder")
    return names


def _profile(p, stats, style_stats, n_clusters, rules, pct_prefix):
    """Cluster each position on its style stats; percentiles within position."""
    frames, summary = [], {}
    for pos, cols in style_stats.items():
        idx = p.index[p["pos"] == pos]
        if len(idx) < 10:  # too few players to form styles
            continue
        s = stats.loc[idx, cols]
        pct = stats.loc[idx, list(dict.fromkeys(sum(style_stats.values(), [])))].rank(pct=True) * 100
        if pos == "GK":
            # ~20 keepers is too few to cluster; compare their shot-stopping and sweeping instead.
            f = pd.DataFrame(index=idx)
            stop = pct[["saves", "goals_prevented"]].mean(axis=1)
            sweep = pct[["xGBuildup", "recoveries"]].mean(axis=1)
            f["style"] = np.where(stop >= sweep, "Shot-stopper", "Sweeper keeper")
            for c in pct.columns:
                f[f"{pct_prefix}{c}"] = pct[c].round(0)
            frames.append(f)
            continue
        z = pd.DataFrame(StandardScaler().fit_transform(s), index=idx, columns=cols)
        km = KMeans(n_clusters[pos], n_init=20, random_state=0).fit(z)
        cent = pd.DataFrame(km.cluster_centers_, columns=cols)
        names = name_clusters(pos, cent, rules)
        f = pd.DataFrame(index=idx)
        f["style"] = [names[c] for c in km.labels_]
        for c in pct.columns:
            f[f"{pct_prefix}{c}"] = pct[c].round(0)
        frames.append(f)
        summary[pos] = {names[i]: {c: round(float(cent.at[i, c]), 2) for c in cols}
                        for i in range(n_clusters[pos])}
    return pd.concat(frames), summary


def build() -> tuple[pd.DataFrame, dict]:
    p = pd.read_parquet(DATA / "players.parquet")
    p = p[p["win_time"] >= MIN_MINUTES].copy()
    p["win_minutes"] = p["win_time"]
    stats = per90(p)
    epl = p["league"] == "EPL"
    # Goalkeepers can only be judged where we have saves data (the Premier League).
    keep = epl | (p["pos"] != "GK")
    p, stats = p[keep], stats[keep]
    epl = epl[keep]

    # Full profile (defensive stats included) for the Premier League...
    full, full_summary = _profile(p[epl], stats[epl], STYLE_STATS, N_CLUSTERS, STYLE_RULES, "pct_")
    # ...and an attacking/creative profile that works across all five leagues.
    att, att_summary = _profile(p[p.pos != "GK"], stats[p.pos != "GK"], ATT_STATS, N_CLUSTERS_ATT,
                                ATT_RULES, "pct_eu_")

    base = p[["pid", "code", "league", "league_name", "name", "web_name", "team", "pos", "age",
              "win_minutes", "tm_value"]]
    res = pd.concat([base, stats.add_prefix("p90_").round(3)], axis=1)
    res = res.join(full.add_suffix("_full")).join(att.add_suffix("_att"))
    # Each player's style: the richer Premier League profile where we have it.
    res["style"] = res["style_full"].fillna(res["style_att"])
    res["profile"] = np.where(res["style_full"].notna(), "full", "attacking")
    res = res.rename(columns=lambda c: c.removesuffix("_att") if c.startswith("pct_eu_") else
                     (c.removesuffix("_full") if c.startswith("pct_") else c))
    return res.drop(columns=["style_full", "style_att"]).reset_index(drop=True), \
        {"full": full_summary, "attacking": att_summary}


def main():
    df, summary = build()
    df.to_parquet(DATA / "scout.parquet", index=False)
    meta = {"labels": {k: v[2] for k, v in STATS.items()}, "style_stats": STYLE_STATS,
            "att_stats": ATT_STATS, "clusters": summary, "min_minutes": MIN_MINUTES}
    (DATA / "scout_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"scout: {len(df)} players")
    print(df.groupby(["profile", "pos", "style"]).size().to_string())


if __name__ == "__main__":
    main()
