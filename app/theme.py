"""Colours in one place: league palettes, fixed meanings and chart helpers.

Each league has two deep colours (`a`, `b`) that white text can sit on, and a bright `hi`
used only for decoration (underlines, glows, rings), never behind text."""

BRAND = {"a": "#0A5C40", "b": "#0C7A54", "hi": "#2BE07F"}
LEAGUE_THEME = {
    "EPL": {"a": "#37003C", "b": "#9C0050", "hi": "#FF2882"},
    "La_Liga": {"a": "#A31F0C", "b": "#C2410C", "hi": "#FF9F1C"},
    "Serie_A": {"a": "#0A2A6B", "b": "#005FA8", "hi": "#33B5FF"},
    "Bundesliga": {"a": "#7A0A10", "b": "#C8102E", "hi": "#FF4D5A"},
    "Ligue_1": {"a": "#091C3E", "b": "#1B3A7A", "hi": "#DAE025"},
}

# Fixed meanings, the same on every page.
HOME, DRAW, AWAY = "#0C7A54", "#6B7570", "#3F6FD8"
GOOD, CAUTION, BAD, NEUTRAL = "#0C7A54", "#B7791F", "#C2410C", "#8A948F"


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


def league_scale(key: str | None) -> list:
    """Heatmap colour scale: pale tint of the league colour up to its deepest shade."""
    t = league(key)
    return [[0, mix(t["b"], "#FFFFFF", 0.93)], [0.45, mix(t["b"], "#FFFFFF", 0.45)], [1, t["a"]]]


def style_chart(fig, height: int | None = None):
    """Shared Plotly look: heading font for titles, transparent background, calm margins."""
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      hoverlabel=dict(font_size=13), margin=dict(l=0, r=0, t=10, b=0))
    if height:
        fig.update_layout(height=height)
    return fig
