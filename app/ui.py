"""Small shared UI pieces in the FootyMinds look (inspired by krackerz.com).

Colours come from app/theme.py and the stylesheet lives in app/style.css. The league touch
(--lg-a/--lg-b/--lg-hi, set per page by `set_league_accent`) colours the league sticker and the
heatmaps. Everything animated is also readable with animations off, and `prefers-reduced-motion`
switches them all off."""
import html
from pathlib import Path

import pandas as pd
import streamlit as st

from app import data, theme

HOME, DRAW, AWAY = theme.HOME, theme.DRAW, theme.AWAY
FAVOUR_HOME, FAVOUR_AWAY = HOME, AWAY
_HERE = Path(__file__).parent

def _css() -> str:
    return "<style>\n" + (_HERE / "style.css").read_text(encoding="utf-8") + "\n</style>"


CSS = _css()

BALL_IMG = '<img class="ball" src="app/static/ball.png" alt="">'  # st.html strips inline SVG


def inject_css():
    st.html(_css())  # read each run, so style edits show without a restart


def inject_motion():
    js = (_HERE / "motion.js").read_text(encoding="utf-8")
    st.html(f"<script>{js}</script>", unsafe_allow_javascript=True)


def set_league_accent(league: str | None):
    """The league touch: this league's colours for its sticker and the heatmaps."""
    t = theme.league(league)
    st.html(f"<style>:root{{--lg-a:{t['a']};--lg-b:{t['b']};--lg-hi:{t['hi']}}}</style>")


def money(v) -> str:
    if v is None or pd.isna(v):
        return "–"
    if v >= 1e6:
        return f"€{v / 1e6:.0f}m" if v >= 1e7 else f"€{v / 1e6:.1f}m"
    return f"€{v / 1e3:.0f}k"


def num(text: str) -> str:
    """A number that counts up when it comes into view. The text is always there for screen readers."""
    return f'<span data-count><span>{html.escape(text)}</span></span>'


def sticker(text: str, kind: str = "ink", tilt: float = -3) -> str:
    """A slapped-on label: ink (lime text), red, lime or league (the league's colour)."""
    return f'<span class="fm-sticker {kind}" style="--tilt:{tilt}deg">{html.escape(text)}</span>'


def eyebrow(text: str):
    """Red scalloped label above a section heading."""
    st.html(f'<span class="fm-eyebrow">{html.escape(text)}</span>')


def hero(title_html: str, sub: str = "", tag: str = "", ball: bool = True):
    """Big centred headline on a white cloud. `title_html` may use <em> for the script word."""
    st.html('<div class="fm-hero">' + (BALL_IMG if ball else "")
            + (sticker(tag, "ink", -3) if tag else "")
            + f"<h1>{title_html}</h1>" + (f"<p>{html.escape(sub)}</p>" if sub else "") + "</div>")


def badge(team: str) -> str:
    c = data.club_colours().get(team, "#888")
    return f'<span class="ml-badge"><span class="ml-dot" style="background:{c}"></span>{html.escape(team)}</span>'


def club_stripe(home: str, away: str | None = None) -> str:
    """Stripe across the top of a card in one or two clubs' colours."""
    colours = data.club_colours()
    h = colours.get(home, "#888")
    bg = f"linear-gradient(90deg,{h} 0 50%,{colours.get(away, '#888')} 50% 100%)" if away else h
    return f'<div class="fm-stripe" style="background:{bg}"></div>'


def banner(title: str, sub: str = "") -> str:
    """Red block with the league sticker (in the league's own colour) and a line of context."""
    return (f'<div class="fm-banner">{sticker(title, "league", -2)}'
            + (f'<span class="s">{html.escape(sub)}</span>' if sub else "") + "</div>")


def ring(pct: float, label: str = "") -> str:
    """Circular gauge that fills to `pct` (0–100)."""
    p = max(0.0, min(100.0, float(pct)))
    return (f'<div class="fm-ring" style="--fm-p:{p:.1f}" role="img" aria-label="{html.escape(label or f"{p:.0f}%")}">'
            f'{num(f"{p:.0f}%")}</div>')


def prob_bar(home: str, away: str, p_h: float, p_d: float, p_a: float, big: bool = False) -> str:
    h, d, a = (round(100 * x) for x in (p_h, p_d, p_a))
    style = ' style="height:46px;font-size:1rem"' if big else ""

    def seg(pct, colour, text):
        t = text if pct >= 12 else (f"{pct}%" if pct >= 7 else "")
        return (f'<div style="width:{pct}%;background:{colour};color:{theme.text_on(colour)}">'
                f'{num(t) if t else ""}</div>')

    return (f'<div class="ml-bar"{style}>{seg(h, HOME, f"{h}%")}{seg(d, DRAW, f"Draw {d}%" if d >= 25 else f"{d}%")}'
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
    for k, (label, v) in enumerate(items):
        w = min(50, 50 * abs(v) / scale)
        colour = FAVOUR_HOME if v > 0 else FAVOUR_AWAY
        pos = f"left:50%;width:{w}%" if v > 0 else f"left:{50 - w}%;width:{w}%"
        body.append(f'<div>{html.escape(label)}</div><div class="ml-track"><span class="mid"></span>'
                    f'<span class="fill{"" if v > 0 else " neg"}" style="{pos};background:{colour};'
                    f'animation-delay:{0.15 + 0.08 * k:.2f}s"></span></div>'
                    f'<div class="ml-val">{v:+.0f}{unit}</div>')
    return (f'<div class="ml-why" style="grid-template-columns:1fr auto 1fr;margin-bottom:.3rem">{"".join(rows)}</div>'
            f'<div class="ml-why">{"".join(body)}</div>')


def parse_scores(top_scores: str) -> list[tuple[str, float]]:
    """'1-0:0.1390|2-0:0.1325|...' -> [('1–0', 0.139), ...]"""
    out = []
    for part in str(top_scores).split("|"):
        if ":" in part:
            s, p = part.split(":")
            out.append((s.replace("-", "–"), float(p)))
    return out


def score_chips(top_scores: str, n: int = 5) -> str:
    chips = []
    for k, (s, p) in enumerate(parse_scores(top_scores)[:n]):
        chips.append(f'<span class="ml-pill ml-chip{" best" if k == 0 else ""}" '
                     f'style="animation-delay:{0.1 + 0.09 * k:.2f}s">{s} · {p:.0%}</span>')
    return '<div style="display:flex;flex-wrap:wrap;padding:.3rem 0">' + "".join(chips) + "</div>"


def pill(text: str, colour: str, shine: bool = False) -> str:
    """A small tilted sticker in `colour` (text in ink or white, whichever reads better)."""
    return (f'<span class="ml-pill{" shine" if shine else ""}" '
            f'style="background:{colour};color:{theme.text_on(colour)}">{html.escape(text)}</span>')


def player_picker(label: str, pids: list[int], key: str = "player", default: int | None = None,
                  help: str | None = None) -> int | None:
    """Searchable player box whose choice lives in the URL (?player=...), so links are shareable."""
    labels = data.player_index().set_index("pid")["label"].to_dict()
    pids = [c for c in pids if c in labels]
    idx = pids.index(default) if default in pids else (0 if pids else None)
    return st.selectbox(label, pids, index=idx, format_func=lambda c: labels.get(c, str(c)),
                        key=key, bind="query-params", placeholder="Type a player's name…", help=help)


def player_search(key: str, label: str = "Find any player"):
    """Search box for any player in the top five leagues, with links to his value, look-alikes and compare."""
    pages = st.session_state["pages"]
    idx = data.player_index()
    labels = idx.set_index("pid")["label"].to_dict()
    found = st.selectbox(label, idx["pid"].tolist(), index=None, format_func=lambda c: labels[c],
                         placeholder="Type a name: Saka, Yamal, Kane…", key=key)
    if found is not None:
        q = {"player": labels[found]}  # bound widgets read their label from the URL
        c1, c2, c3 = st.columns(3)
        c1.page_link(pages["value"], label="What's he worth?", icon=":material/payments:", query_params=q)
        c2.page_link(pages["scout"], label="Similar players", icon=":material/person_search:", query_params=q)
        c3.page_link(pages["compare"], label="Compare him", icon=":material/compare_arrows:",
                     query_params={"players": labels[found]})
    return found


def footer():
    """Maroon footer: wordmark, what's covered, when it was updated, and the small print."""
    m = data.meta("meta")
    when = f" · updated {pd.Timestamp(m['updated_at']).strftime('%d %b %Y')}" if m else ""
    season = f"{m['season']} · " if m else ""
    st.html('<div class="fm-footer"><span class="w">Footy<b>Minds</b></span>'
            + sticker("Europe's top 5", "lime", 3)
            + f"<p>{html.escape(season)}Premier League, La Liga, Serie A, Bundesliga, Ligue 1{html.escape(when)}</p>"
            "<p>Data: Understat, football-data.co.uk, Fantasy Premier League and Transfermarkt.</p>"
            "<p>Match events: ESPN. Highlights: official league channels on YouTube.</p>"
            "<p>Not affiliated with any league, club or FPL. Just for fun, not betting advice.</p></div>")
    from app import votes  # the device id cookie is written once, here at the bottom of every page
    votes.write_cookies()
    inject_motion()


def league_picker(key: str = "league") -> str:
    """Premier League · La Liga · Serie A · Bundesliga · Ligue 1. Lives in the URL (?league=...)
    and is remembered across pages; links without it mean the Premier League."""
    lg = data.leagues()
    # A shared link naming a club (e.g. ?home=Barcelona) picks that club's league.
    if key not in st.query_params:
        for q in ("home", "away"):
            team = st.query_params.get(q)
            if team and team in data.team_league():
                st.session_state[key] = data.team_league()[team]
                break
    league = st.segmented_control("League", list(lg), format_func=lambda k: lg[k]["name"],
                                  default=data.DEFAULT_LEAGUE, required=True, key=key,
                                  bind="query-params", persist_state="session",
                                  label_visibility="collapsed")
    set_league_accent(league)
    return league


def league_filter(label: str = "League", key: str = "league_filter") -> str | None:
    """All leagues, or just one (for lists and search results). None = all."""
    lg = data.leagues()
    opts = ["all"] + list(lg)
    choice = st.segmented_control(label, opts, default="all", required=True, key=key,
                                  format_func=lambda k: "All top 5" if k == "all" else lg[k]["name"])
    return None if choice == "all" else choice


def team_picker(label: str, key: str, default: str, league: str | None = None) -> str:
    teams = data.teams(league)
    return st.selectbox(label, teams, index=teams.index(default) if default in teams else 0,
                        key=key, bind="query-params")


def missing(what: str):
    st.info(f"{what} isn't available right now — the weekly data refresh may still be running. "
            "Please check back soon.")


def how_it_works(md: str):
    with st.expander("How does this work?"):
        st.markdown(md)
