"""Colours in one place: the Krackerz-inspired palette, fixed meanings and chart helpers.

Cream paper, ink, tomato red down to deep maroon, and neon lime for stickers and buttons.
League colours survive only as an accent (the league sticker and heatmap shading)."""

PAPER, CARD, INK, STONE = "#F7F6F0", "#FFFFFF", "#161616", "#D9D3C7"
RED, RUST, MAROON, DEEP = "#CF2B09", "#A52207", "#7C1A06", "#580D14"
LIME, LIME_DARK = "#C8FF2E", "#5E7F00"
TILE_SHADES = [RED, RUST, MAROON, DEEP]  # number tiles across a row

# Fixed meanings, the same on every page. Labels always accompany colour.
HOME, DRAW, AWAY = RED, STONE, INK
GOOD, NEUTRAL, BAD = LIME, STONE, RED

BRAND = {"a": DEEP, "b": RED, "hi": LIME}
LEAGUE_THEME = {
    "EPL": {"a": "#37003C", "b": "#9C0050", "hi": "#FF2882"},
    "La_Liga": {"a": "#A31F0C", "b": "#C2410C", "hi": "#FF9F1C"},
    "Serie_A": {"a": "#0A2A6B", "b": "#005FA8", "hi": "#33B5FF"},
    "Bundesliga": {"a": "#7A0A10", "b": "#C8102E", "hi": "#FF4D5A"},
    "Ligue_1": {"a": "#091C3E", "b": "#1B3A7A", "hi": "#DAE025"},
}
CHART = [RED, INK, LIME_DARK, MAROON, "#D97706", "#6B645C"]


def league(key: str | None) -> dict:
    return LEAGUE_THEME.get(key or "", BRAND)


def _rgb(hex_: str) -> tuple[int, int, int]:
    h = hex_.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(c1: str, c2: str, t: float) -> str:
    """Blend two hex colours: t=0 gives c1, t=1 gives c2."""
    a, b = _rgb(c1), _rgb(c2)
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def luminance(hex_: str) -> float:
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in _rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(c1: str, c2: str) -> float:
    hi, lo = sorted((luminance(c1), luminance(c2)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def text_on(bg: str) -> str:
    """Ink or white, whichever reads better on `bg`."""
    return INK if contrast(INK, bg) >= contrast("#FFFFFF", bg) else "#FFFFFF"


def league_scale(key: str | None) -> list:
    """Heatmap colour scale: paper up to the league's deepest shade (the league touch)."""
    t = league(key)
    return [[0, mix(t["b"], PAPER, 0.94)], [0.45, mix(t["b"], PAPER, 0.45)], [1, t["a"]]]


def style_chart(fig, height: int | None = None):
    """Shared Plotly look: DM Sans, the palette, transparent background, calm margins."""
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", colorway=CHART,
                      font=dict(family="DM Sans, sans-serif", color=INK),
                      hoverlabel=dict(font_size=13, font_family="DM Sans, sans-serif"))
    if fig.layout.margin.l is None:  # keep margins a chart sets itself (the radar needs room for labels)
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0))
    if height:
        fig.update_layout(height=height)
    return fig
