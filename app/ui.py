"""Small shared UI pieces. HTML uses `inherit`/translucent colours so it works in light and dark.

Colours come from app/theme.py. The stylesheet below adds the league accent (CSS variables
--lg-a/--lg-b/--lg-hi, set per page by `set_league_accent`) and the motion: entrances, growing
bars, count-ups, hover lifts. Everything animated is also readable with animations off, and
`prefers-reduced-motion` switches them all off."""
import html
from pathlib import Path

import pandas as pd
import streamlit as st

from app import data, theme

HOME, DRAW, AWAY = theme.HOME, theme.DRAW, theme.AWAY
FAVOUR_HOME, FAVOUR_AWAY = HOME, AWAY


def _stagger(selector: str, n: int, start: float, step: float) -> str:
    return "".join(f"{selector}:nth-child({i + 1}){{animation-delay:{start + i * step:.2f}s}}" for i in range(n))


TOP = "[data-testid=stMainBlockContainer]>[data-testid=stVerticalBlock]>*"
CARD = "[data-testid=stColumn]>[data-testid=stVerticalBlock]>*"

CSS = """
<style>
/* No "<" + letter anywhere in here: Streamlit's sanitiser drops style blocks that look like they hold tags. */
@property --fm-p{syntax:'\\3C number>';inherits:true;initial-value:0}
:root{--lg-a:%(a)s;--lg-b:%(b)s;--lg-hi:%(hi)s;--fm-ease:cubic-bezier(.2,.8,.2,1);--fm-live:#E5484D}

@keyframes fm-rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:none}}
@keyframes fm-fade{from{opacity:0}to{opacity:1}}
@keyframes fm-wipe{from{clip-path:inset(0 100%% 0 0)}to{clip-path:inset(0 0 0 0)}}
@keyframes fm-grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes fm-pop{0%%{opacity:0;transform:scale(.7)}70%%{opacity:1;transform:scale(1.06)}100%%{opacity:1;transform:none}}
@keyframes fm-pulse{0%%{box-shadow:0 0 0 0 rgba(229,72,77,.6)}70%%{box-shadow:0 0 0 7px rgba(229,72,77,0)}100%%{box-shadow:0 0 0 0 rgba(229,72,77,0)}}
@keyframes fm-shine{0%%,55%%{transform:translateX(-130%%)}100%%{transform:translateX(230%%)}}
@keyframes fm-sheen{from{transform:translateX(-100%%)}to{transform:translateX(100%%)}}
@keyframes fm-ring{from{--fm-p:0}}
@keyframes fm-spin{to{transform:rotate(360deg)}}
@keyframes fm-roll{from{opacity:0;transform:translateX(-36px) rotate(-360deg)}to{opacity:1;transform:none}}

/* Page content arrives in sequence; cards in columns cascade. */
%(top)s{animation:fm-rise .55s var(--fm-ease) both}
%(top_delays)s
%(card)s{animation:fm-rise .5s var(--fm-ease) both}
%(card_delays)s
[data-testid=stColumn]:nth-child(2)>[data-testid=stVerticalBlock]>*{animation-duration:.6s}
/* Further down the page, sections reveal as they scroll into view (where the browser supports it). */
@supports (animation-timeline: view()){
  %(top)s:nth-child(n+9){animation:fm-rise linear both;animation-timeline:view();animation-range:entry 0%% entry 40%%}
}
[data-testid=stPlotlyChart]{animation:fm-fade .9s .15s ease both}
[data-testid=stDataFrame]{animation:fm-fade .7s .1s ease both}

/* Headings: sporty font (config.toml), a league-colour underline that draws in, a marker on sections. */
[data-testid=stMainBlockContainer] [data-testid=stHeading] h1::after{content:"";display:block;height:4px;width:72px;
  margin-top:.4rem;border-radius:4px;background:linear-gradient(90deg,var(--lg-b),var(--lg-hi));transform-origin:left;
  animation:fm-grow .8s .25s var(--fm-ease) both}
[data-testid=stMainBlockContainer] [data-testid=stHeading] h3::before{content:"";display:inline-block;width:6px;height:.85em;
  border-radius:3px;margin-right:.5rem;vertical-align:-.04em;background:linear-gradient(180deg,var(--lg-hi),var(--lg-b))}

/* Metric tiles: soft league tint, pop in, lift on hover. */
[data-testid=stMetric]{border-radius:12px;padding:.65rem .9rem;border:1px solid color-mix(in srgb,var(--lg-b) 22%%,transparent);
  background:linear-gradient(135deg,color-mix(in srgb,var(--lg-b) 11%%,transparent),color-mix(in srgb,var(--lg-hi) 4%%,transparent));
  animation:fm-pop .5s .1s var(--fm-ease) both;transition:transform .2s var(--fm-ease),box-shadow .2s}
[data-testid=stMetric]:hover{transform:translateY(-2px);box-shadow:0 8px 20px -10px color-mix(in srgb,var(--lg-b) 70%%,transparent)}

/* Cards (containers keyed "fmcard...") lift with a coloured shadow. */
[class*="st-key-fmcard"]{transition:transform .25s var(--fm-ease),box-shadow .25s,border-color .25s;overflow:hidden}
[class*="st-key-fmcard"]:hover{transform:translateY(-3px);border-color:color-mix(in srgb,var(--lg-b) 45%%,transparent);
  box-shadow:0 14px 30px -16px color-mix(in srgb,var(--lg-b) 80%%,transparent)}

/* Controls pick up the league colour. */
[data-testid=stButtonGroup] button{transition:transform .15s var(--fm-ease),box-shadow .2s}
[data-testid=stButtonGroup] button:hover{transform:translateY(-1px)}
[data-testid=stButtonGroup] button[aria-checked=true]{background:linear-gradient(120deg,var(--lg-a),var(--lg-b))!important;
  border-color:var(--lg-hi)!important;box-shadow:0 4px 14px -6px var(--lg-b)}
[data-testid=stButtonGroup] button[aria-checked=true] *{color:#fff!important}
[data-baseweb=tab-highlight]{background:linear-gradient(90deg,var(--lg-b),var(--lg-hi))!important}
[data-testid=stPageLink-NavLink]{transition:transform .2s var(--fm-ease),background-color .2s}
[data-testid=stMainBlockContainer] [data-testid=stPageLink-NavLink]:hover{transform:translateX(4px);
  background:color-mix(in srgb,var(--lg-b) 10%%,transparent)}
[data-testid=stSidebarNavLink]{transition:background-color .2s,transform .2s var(--fm-ease)}
[data-testid=stSidebarNavLink]:hover{transform:translateX(3px);background:color-mix(in srgb,var(--lg-b) 12%%,transparent)}
[data-testid=stExpander] details{transition:border-color .25s}
[data-testid=stExpander] details:hover{border-color:color-mix(in srgb,var(--lg-b) 45%%,transparent)}
[data-testid=stSpinnerIcon]{display:none}
[data-testid=stSpinner]>div::before{content:"⚽";display:inline-block;margin-right:.5rem;animation:fm-spin .9s linear infinite}

/* Our own pieces. */
.ml-bar{display:flex;height:34px;border-radius:8px;overflow:hidden;font-weight:600;font-size:.85rem;margin:.35rem 0 .2rem;
  animation:fm-wipe .9s .2s var(--fm-ease) both}
.ml-bar div{display:flex;align-items:center;justify-content:center;color:#fff;white-space:nowrap;overflow:hidden}
.ml-legend{display:flex;justify-content:space-between;font-size:.8rem;opacity:.75}
.ml-badge{display:inline-flex;align-items:center;gap:.4rem;font-weight:600}
.ml-dot{width:.8rem;height:.8rem;border-radius:50%%;display:inline-block;flex:none;box-shadow:0 0 0 1px rgba(128,128,128,.4)}
.ml-why{display:grid;grid-template-columns:minmax(120px,1.1fr) 2fr 3.5rem;gap:.35rem .6rem;align-items:center;font-size:.9rem}
.ml-track{position:relative;height:14px;background:rgba(128,128,128,.14);border-radius:7px}
.ml-track .mid{position:absolute;left:50%%;top:-3px;bottom:-3px;width:1px;background:rgba(128,128,128,.6)}
.ml-track .fill{position:absolute;top:0;bottom:0;border-radius:7px;transform-origin:left;animation:fm-grow .75s var(--fm-ease) both}
.ml-track .fill.neg{transform-origin:right}
.ml-val{text-align:right;font-variant-numeric:tabular-nums;opacity:.85}
.ml-pill{display:inline-block;padding:.15rem .6rem;border-radius:999px;font-weight:700;font-size:.85rem}
.ml-pill.shine{position:relative;overflow:hidden;vertical-align:middle}
.ml-pill.shine::after{content:"";position:absolute;inset:0;transform:translateX(-130%%);
  background:linear-gradient(100deg,transparent 30%%,rgba(255,255,255,.7) 50%%,transparent 70%%);animation:fm-shine 3.2s ease-in-out infinite}
.ml-chip{animation:fm-pop .45s var(--fm-ease) both;background:rgba(128,128,128,.12);border:1px solid rgba(128,128,128,.35);
  margin:0 .35rem .35rem 0}
.ml-chip.best{font-size:1.05rem;border-color:var(--lg-hi);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--lg-hi) 22%%,transparent),0 6px 18px -8px var(--lg-hi)}
.ml-card{border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:.8rem 1rem;margin-bottom:.4rem}
.ml-muted{opacity:.7;font-size:.85rem}
.fm-live{display:inline-block;width:.5rem;height:.5rem;border-radius:50%%;background:var(--fm-live);margin-right:.4rem;
  vertical-align:.05em;animation:fm-pulse 1.8s ease-out infinite}
.fm-soon{color:var(--fm-live);font-weight:700;opacity:1}
.fm-stripe{height:5px;margin:-1rem -1rem .75rem;transform-origin:left;animation:fm-grow .7s .15s var(--fm-ease) both}
.fm-banner{position:relative;overflow:hidden;border-radius:14px;padding:.85rem 1.2rem;color:#fff;
  background:linear-gradient(120deg,var(--lg-a),var(--lg-b));border-left:6px solid var(--lg-hi);
  display:flex;justify-content:space-between;align-items:center;gap:.4rem 1rem;flex-wrap:wrap;
  box-shadow:0 12px 30px -20px var(--lg-b)}
.fm-banner::before{content:"";position:absolute;inset:0;pointer-events:none;
  background:repeating-linear-gradient(90deg,rgba(255,255,255,.035) 0 44px,transparent 44px 88px)}
.fm-banner::after{content:"";position:absolute;inset:0;pointer-events:none;transform:translateX(-100%%);
  background:linear-gradient(100deg,transparent 35%%,rgba(255,255,255,.22) 50%%,transparent 65%%);animation:fm-sheen 1.6s .35s ease-out both}
.fm-banner .t{position:relative;font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:1.65rem;
  letter-spacing:.06em;text-transform:uppercase;line-height:1.05}
.fm-banner .s{position:relative;font-size:.9rem;opacity:.92}
.fm-ring{position:relative;width:58px;height:58px;display:grid;place-items:center;font-weight:700;font-size:.95rem;
  font-variant-numeric:tabular-nums;animation:fm-ring 1.1s .2s var(--fm-ease) both}
.fm-ring::before{content:"";position:absolute;inset:0;border-radius:50%%;
  background:conic-gradient(var(--lg-b) 0,var(--lg-hi) calc(var(--fm-p) * 1%%),rgba(128,128,128,.18) calc(var(--fm-p) * 1%%));
  -webkit-mask:radial-gradient(farthest-side,transparent calc(100%% - 7px),#000 calc(100%% - 6px));
  mask:radial-gradient(farthest-side,transparent calc(100%% - 7px),#000 calc(100%% - 6px))}
.fm-wordmark{font-family:'Barlow Condensed',sans-serif;font-weight:800;font-size:1.9rem;letter-spacing:.04em;line-height:1;
  display:flex;align-items:center;gap:.45rem;margin:.1rem 0 .6rem}
.fm-wordmark .ball{display:inline-block;animation:fm-roll 1.1s var(--fm-ease) both}
.fm-wordmark b{font-weight:800;background:linear-gradient(90deg,#0C7A54,#16A06A);-webkit-background-clip:text;background-clip:text;color:transparent}
@media (prefers-color-scheme: dark){.fm-wordmark b{background-image:linear-gradient(90deg,#16A06A,#2BE07F)}}

/* Count-ups (see MOTION_JS): the real text is hidden only while the animated copy plays. */
[data-fm-counting]{position:relative}
[data-fm-counting]>*{visibility:hidden}
[data-fm-counting]::after{content:attr(data-fm-show);position:absolute;left:0;top:0;white-space:nowrap}

@media (max-width: 640px){[data-testid=stMainBlockContainer] [data-testid=stHeading] h1{font-size:2.3rem}
  .fm-banner .t{font-size:1.35rem}}
@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
}
</style>
""" % {"a": theme.BRAND["a"], "b": theme.BRAND["b"], "hi": theme.BRAND["hi"], "top": TOP, "card": CARD,
       "top_delays": _stagger(TOP, 12, 0, 0.05), "card_delays": _stagger(CARD, 10, 0.12, 0.07)}

# Counts numbers up from zero the first time they scroll into view (and again if they change).
# It only reads our own page text and never writes to elements React manages: the animated copy is
# shown through a data attribute + ::after, so nothing breaks if it stops half-way.
MOTION_JS = (Path(__file__).with_name("motion.js")).read_text(encoding="utf-8")


def inject_css():
    st.html(CSS)


def inject_motion():
    st.html(f"<script>{MOTION_JS}</script>", unsafe_allow_javascript=True)


def set_league_accent(league: str | None):
    """Colour the page in this league's palette (FootyMinds green when there's no league)."""
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


def badge(team: str) -> str:
    c = data.club_colours().get(team, "#888")
    return f'<span class="ml-badge"><span class="ml-dot" style="background:{c}"></span>{html.escape(team)}</span>'


def club_stripe(home: str, away: str | None = None) -> str:
    """Thin stripe across the top of a card in one or two clubs' colours."""
    colours = data.club_colours()
    h = colours.get(home, "#888")
    bg = f"linear-gradient(90deg,{h} 0 50%,{colours.get(away, '#888')} 50% 100%)" if away else h
    return f'<div class="fm-stripe" style="background:{bg}"></div>'


def banner(title: str, sub: str = "") -> str:
    """Gradient banner in the current league's colours."""
    return (f'<div class="fm-banner"><span class="t">{html.escape(title)}</span>'
            + (f'<span class="s">{html.escape(sub)}</span>' if sub else "") + "</div>")


def ring(pct: float, label: str = "") -> str:
    """Circular gauge that fills to `pct` (0–100)."""
    p = max(0.0, min(100.0, float(pct)))
    return (f'<div class="fm-ring" style="--fm-p:{p:.1f}" role="img" aria-label="{html.escape(label or f"{p:.0f}%")}">'
            f'{num(f"{p:.0f}%")}</div>')


def prob_bar(home: str, away: str, p_h: float, p_d: float, p_a: float, big: bool = False) -> str:
    h, d, a = (round(100 * x) for x in (p_h, p_d, p_a))
    style = ' style="height:44px;font-size:1rem"' if big else ""

    def seg(pct, colour, text):
        t = text if pct >= 12 else (f"{pct}%" if pct >= 7 else "")
        return f'<div style="width:{pct}%;background:{colour}">{num(t) if t else ""}</div>'

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
    return '<div style="display:flex;flex-wrap:wrap">' + "".join(chips) + "</div>"


def pill(text: str, colour: str, shine: bool = False) -> str:
    return (f'<span class="ml-pill{" shine" if shine else ""}" '
            f'style="background:{colour}22;color:{colour};border:1px solid {colour}66">{html.escape(text)}</span>')


def player_picker(label: str, pids: list[int], key: str = "player", default: int | None = None,
                  help: str | None = None) -> int | None:
    """Searchable player box whose choice lives in the URL (?player=...), so links are shareable."""
    labels = data.player_index().set_index("pid")["label"].to_dict()
    pids = [c for c in pids if c in labels]
    idx = pids.index(default) if default in pids else (0 if pids else None)
    return st.selectbox(label, pids, index=idx, format_func=lambda c: labels.get(c, str(c)),
                        key=key, bind="query-params", placeholder="Type a player's name…", help=help)


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
