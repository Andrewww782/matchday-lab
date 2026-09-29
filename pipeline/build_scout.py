"""Per-90 style profiles, playing-style clusters and percentiles for Scout + Compare."""
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
    out = pd.DataFrame(index=df.index)
    for k, (col, mins, _) in STATS.items():
        m = df[mins].clip(lower=1)
        if k == "goals_prevented":  # xG faced minus goals let in, per 90
            out[k] = (df["win_expected_goals_conceded"] - df["win_goals_conceded"]) / m * 90
        else:
            out[k] = df[col].fillna(0) / m * 90
    return out


def name_clusters(pos: str, centroids: pd.DataFrame) -> dict[int, str]:
    """Give each cluster the best-fitting style name (each name used once)."""
    rules = [(w, n) for p, w, n in STYLE_RULES if p == pos]
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


def build() -> tuple[pd.DataFrame, dict]:
    p = pd.read_parquet(DATA / "players.parquet")
    p = p[p["win_minutes"] >= MIN_MINUTES].copy()
    stats = per90(p)
    out = [p[["code", "name", "web_name", "team", "pos", "age", "win_minutes", "tm_value"]]]
    frames, summary = [], {}
    for pos, cols in STYLE_STATS.items():
        idx = p.index[p["pos"] == pos]
        s = stats.loc[idx, cols]
        z = pd.DataFrame(StandardScaler().fit_transform(s), index=idx, columns=cols)
        km = KMeans(N_CLUSTERS[pos], n_init=20, random_state=0).fit(z)
        cent = pd.DataFrame(km.cluster_centers_, columns=cols)
        names = name_clusters(pos, cent)
        f = pd.DataFrame(index=idx)
        f["style"] = [names[c] for c in km.labels_]
        for c in cols:
            f[f"z_{c}"] = z[c]
        pct = stats.loc[idx].rank(pct=True) * 100
        for c in STATS:
            f[f"pct_{c}"] = pct[c].round(0)
        frames.append(f)
        summary[pos] = {names[i]: {c: round(float(cent.at[i, c]), 2) for c in cols}
                        for i in range(N_CLUSTERS[pos])}
    styles = pd.concat(frames)
    res = pd.concat([out[0], stats.add_prefix("p90_").round(3)], axis=1).join(styles)
    return res.reset_index(drop=True), summary


def main():
    df, summary = build()
    df.to_parquet(DATA / "scout.parquet", index=False)
    meta = {"labels": {k: v[2] for k, v in STATS.items()}, "style_stats": STYLE_STATS,
            "clusters": summary, "min_minutes": MIN_MINUTES}
    (DATA / "scout_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"scout: {len(df)} players")
    print(df.groupby(["pos", "style"]).size().to_string())


if __name__ == "__main__":
    main()
