export const STREAMLIT = "https://footyminds.streamlit.app";

export const LEAGUE_THEME: Record<string, { a: string; b: string; hi: string }> = {
  EPL: { a: "#37003C", b: "#9C0050", hi: "#FF2882" },
  La_Liga: { a: "#A31F0C", b: "#C2410C", hi: "#FF9F1C" },
  Serie_A: { a: "#0A2A6B", b: "#005FA8", hi: "#33B5FF" },
  Bundesliga: { a: "#7A0A10", b: "#C8102E", hi: "#FF4D5A" },
  Ligue_1: { a: "#091C3E", b: "#1B3A7A", hi: "#DAE025" },
};

export const KIND_LABEL: Record<string, string> = {
  goal_overturned: "VAR · Goal ruled out",
  goal_stands: "VAR · Goal stands",
  var_penalty: "VAR · Penalty given",
  var_no_penalty: "VAR · No penalty",
  var_red: "VAR · Red card",
  var_card_check: "VAR · Card check",
  var_other: "VAR",
  red: "Red card",
  penalty: "Penalty",
  yellow: "Yellow card",
  fan_flag: "Fan flag",
};

const DRAMA: Record<string, number> = {
  goal_overturned: 6,
  var_penalty: 5,
  var_red: 5,
  red: 4,
  penalty: 3,
  var_no_penalty: 2,
};

export function drama(kind: string) {
  return DRAMA[kind] ?? 1;
}

export function money(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "–";
  if (v >= 1e6) return v >= 1e7 ? `€${(v / 1e6).toFixed(0)}m` : `€${(v / 1e6).toFixed(1)}m`;
  return `€${(v / 1e3).toFixed(0)}k`;
}

export function pct(v: number | null | undefined, digits = 0) {
  if (v == null || Number.isNaN(v)) return "–";
  return `${(v * 100).toFixed(digits)}%`;
}

export function whenUK(iso: string | null | undefined, style: "short" | "long" = "short") {
  if (!iso) return "";
  const d = new Date(iso);
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    weekday: style === "long" ? "long" : "short",
    day: "numeric",
    month: style === "long" ? "long" : "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(d) + " UK";
}

export function href(path: string, query?: Record<string, string | number | null | undefined>) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const q = params.toString();
  return q ? `${path}?${q}` : path;
}

export function streamlit(path: string, query?: Record<string, string | undefined>) {
  const url = new URL(path, STREAMLIT);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value) url.searchParams.set(key, value);
  }
  return url.toString();
}

export function one(sp: Record<string, string | string[] | undefined>, key: string) {
  const value = sp[key];
  return Array.isArray(value) ? value[0] : value;
}

export function textOn(bg: string) {
  const h = bg.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  const lin = [r, g, b].map((c) => {
    const x = c / 255;
    return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  });
  const L = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
  const contrast = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  const ink = contrast(0.012, L);
  const white = contrast(1, L);
  return ink >= white ? "#161616" : "#FFFFFF";
}
