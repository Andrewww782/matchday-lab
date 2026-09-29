"""Small shared UI pieces. HTML uses `inherit`/translucent colours so it works in light and dark."""
import html

import pandas as pd
import streamlit as st

from app import data

CLUB_COLOURS = {
    "Arsenal": "#EF0107", "Aston Villa": "#670E36", "Bournemouth": "#B50E12", "Brentford": "#E30613",
    "Brighton": "#0057B8", "Chelsea": "#034694", "Coventry": "#59CBE8", "Crystal Palace": "#1B458F",
    "Everton": "#003399", "Fulham": "#5A5A5A", "Hull": "#F5A12D", "Ipswich": "#3A64A3",
    "Leeds": "#FFCD00", "Liverpool": "#C8102E", "Man City": "#6CABDD", "Man Utd": "#DA291C",
    "Newcastle": "#4A4A4A", "Nott'm Forest": "#DD0000", "Spurs": "#132257", "Sunderland": "#EB172B",
    "Burnley": "#6C1D45", "West Ham": "#7A263A", "Wolves": "#FDB913", "Leicester": "#003090",
    "Southampton": "#D71920",
}
HOME, DRAW, AWAY = "#0E8A5F", "#8A948F", "#3F6FD8"
FAVOUR_HOME, FAVOUR_AWAY = HOME, AWAY

CSS = """
<style>
.ml-bar{display:flex;height:34px;border-radius:8px;overflow:hidden;font-weight:600;font-size:.85rem;margin:.35rem 0 .2rem}
.ml-bar div{display:flex;align-items:center;justify-content:center;color:#fff;white-space:nowrap;overflow:hidden}
.ml-legend{display:flex;justify-content:space-between;font-size:.8rem;opacity:.75}
.ml-badge{display:inline-flex;align-items:center;gap:.4rem;font-weight:600}
.ml-dot{width:.8rem;height:.8rem;border-radius:50%;display:inline-block;flex:none;box-shadow:0 0 0 1px rgba(128,128,128,.4)}
.ml-why{display:grid;grid-template-columns:minmax(120px,1.1fr) 2fr 3.5rem;gap:.35rem .6rem;align-items:center;font-size:.9rem}
.ml-track{position:relative;height:14px;background:rgba(128,128,128,.14);border-radius:7px}
.ml-track .mid{position:absolute;left:50%;top:-3px;bottom:-3px;width:1px;background:rgba(128,128,128,.6)}
.ml-track .fill{position:absolute;top:0;bottom:0;border-radius:7px}
.ml-val{text-align:right;font-variant-numeric:tabular-nums;opacity:.85}
.ml-pill{display:inline-block;padding:.15rem .6rem;border-radius:999px;font-weight:700;font-size:.85rem}
.ml-card{border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:.8rem 1rem;margin-bottom:.4rem}
.ml-muted{opacity:.7;font-size:.85rem}
</style>
"""


def inject_css():
    st.html(CSS)


def money(v) -> str:
    if v is None or pd.isna(v):
        return "–"
    if v >= 1e6:
        return f"€{v / 1e6:.0f}m" if v >= 1e7 else f"€{v / 1e6:.1f}m"
    return f"€{v / 1e3:.0f}k"


def badge(team: str) -> str:
    c = CLUB_COLOURS.get(team, "#888")
    return f'<span class="ml-badge"><span class="ml-dot" style="background:{c}"></span>{html.escape(team)}</span>'


def prob_bar(home: str, away: str, p_h: float, p_d: float, p_a: float, big: bool = False) -> str:
    h, d, a = (round(100 * x) for x in (p_h, p_d, p_a))
    style = ' style="height:44px;font-size:1rem"' if big else ""

    def seg(pct, colour, text):
        t = text if pct >= 12 else (f"{pct}%" if pct >= 7 else "")
        return f'<div style="width:{pct}%;background:{colour}">{t}</div>'

    return (f'<div class="ml-bar"{style}>{seg(h, HOME, f"{h}%")}{seg(d, DRAW, f"Draw {d}%")}'
            f'{seg(a, AWAY, f"{a}%")}</div>'
            f'<div class="ml-legend"><span>{html.escape(home)} win</span><span>Draw</span>'
            f'<span>{html.escape(away)} win</span></div>')


def why_bars(items: list[tuple[str, float]], left: str, right: str, unit: str = " pts",
             scale: float | None = None) -> str:
    """Diverging bars: positive values lean right (e.g. toward the home side)."""
    scale = scale or max([abs(v) for _, v in items] + [1e-9])
    rows = [f'<div class="ml-muted" style="text-align:left">← {html.escape(left)}</div>'
            f'<div></div><div class="ml-muted" style="text-align:right">{html.escape(right)} →</div>']
    body = []
    for label, v in items:
        w = min(50, 50 * abs(v) / scale)
        colour = FAVOUR_HOME if v > 0 else FAVOUR_AWAY
        pos = f"left:50%;width:{w}%" if v > 0 else f"left:{50 - w}%;width:{w}%"
        body.append(f'<div>{html.escape(label)}</div><div class="ml-track"><span class="mid"></span>'
                    f'<span class="fill" style="{pos};background:{colour}"></span></div>'
                    f'<div class="ml-val">{v:+.0f}{unit}</div>')
    return (f'<div class="ml-why" style="grid-template-columns:1fr auto 1fr;margin-bottom:.3rem">{"".join(rows)}</div>'
            f'<div class="ml-why">{"".join(body)}</div>')


def pill(text: str, colour: str) -> str:
    return f'<span class="ml-pill" style="background:{colour}22;color:{colour};border:1px solid {colour}66">{html.escape(text)}</span>'


def player_picker(label: str, codes: list[int], key: str = "player", default: int | None = None,
                  help: str | None = None) -> int | None:
    """Searchable player box whose choice lives in the URL (?player=...), so links are shareable."""
    labels = data.player_index().set_index("code")["label"].to_dict()
    codes = [c for c in codes if c in labels]
    idx = codes.index(default) if default in codes else (0 if codes else None)
    return st.selectbox(label, codes, index=idx, format_func=lambda c: labels.get(c, str(c)),
                        key=key, bind="query-params", placeholder="Type a player's name…", help=help)


def team_picker(label: str, key: str, default: str) -> str:
    teams = data.teams()
    return st.selectbox(label, teams, index=teams.index(default) if default in teams else 0,
                        key=key, bind="query-params")


def missing(what: str):
    st.info(f"{what} isn't available right now — the weekly data refresh may still be running. "
            "Please check back soon.")


def how_it_works(md: str):
    with st.expander("How does this work?"):
        st.markdown(md)
