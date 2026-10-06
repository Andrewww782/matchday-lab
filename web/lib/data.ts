import { one } from "./format";
import siteJson from "../data/site.json";
import fixturesJson from "../data/fixtures.json";
import upcomingJson from "../data/upcoming.json";
import pairsJson from "../data/pairs.json";
import incidentsJson from "../data/incidents.json";
import varMatchesJson from "../data/var_matches.json";
import highlightsJson from "../data/highlights.json";
import playersJson from "../data/players.json";
import valuesJson from "../data/values.json";
import scoutJson from "../data/scout.json";
import stateJson from "../data/state.json";
import tablesJson from "../data/tables.json";

export type League = {
  name: string;
  clubs: number;
  cl: number;
  relegated: number;
  playoff: number | null;
  round: string;
};

export type Site = {
  updatedAt: string | null;
  season: string;
  order: string[];
  leagues: Record<string, League>;
  teams: { league: string; team: string; short: string; colour: string }[];
  about: {
    rows: { league: string; results: string; over: string; score: string; value: string; defence: string }[];
    allModel: string | null;
    allBook: string | null;
    alwaysHome: string | null;
    snapshot: string | null;
  };
  scoutMeta: {
    labels: Record<string, string>;
    styleStats: Record<string, string[]>;
    attStats: Record<string, string[]>;
    minMinutes: number | null;
  };
};

export type Fixture = {
  league: string;
  gw: number;
  kickoff: string;
  home: string;
  away: string;
  hg: number | null;
  ag: number | null;
  finished: boolean;
};

export type Factor = { label: string; v: number };

export type MatchOdds = {
  league: string;
  home: string;
  away: string;
  ph: number;
  pd: number;
  pa: number;
  xgH: number | null;
  xgA: number | null;
  btts: number | null;
  over: number | null;
  csH: number | null;
  csA: number | null;
  scores: { score: string; p: number }[];
  factors: Factor[];
  gw?: number | null;
  kickoff?: string | null;
  id?: string | null;
};

export type Incident = {
  id: string;
  eventId: string;
  league: string;
  gw: number | null;
  kickoff: string | null;
  home: string;
  away: string;
  score: string | null;
  minute: number | null;
  seconds: number | null;
  kind: string;
  big: boolean;
  headline: string;
  player: string | null;
  against: string | null;
  benefit: string | null;
  given: string | null;
};

export type VarMatch = {
  eventId: string;
  league: string;
  gw: number | null;
  kickoff: string | null;
  home: string;
  away: string;
  score: string | null;
  referee: string | null;
};

export type Player = {
  pid: number;
  name: string;
  web: string | null;
  team: string;
  league: string;
  leagueName: string;
  pos: string;
  sub: string | null;
  age: number | null;
  value: number | null;
  minutes: number | null;
  npg: number | null;
  xa: number | null;
  label: string;
};

export type ValueRow = {
  pid: number;
  league: string;
  est: number | null;
  market: number | null;
  ratio: number | null;
  verdict: string;
  factors: Factor[];
};

export type Scout = {
  pid: number;
  name: string;
  web: string | null;
  team: string;
  league: string;
  leagueName: string;
  pos: string;
  age: number | null;
  value: number | null;
  style: string | null;
  minutes: number | null;
  p90: Record<string, number | null>;
  pct: Record<string, number | null>;
  pctEu: Record<string, number | null>;
};

export type TeamState = {
  league: string;
  team: string;
  elo: number | null;
  pts5: number | null;
  xgf5: number | null;
  xga5: number | null;
};

export type TableRow = {
  team: string;
  pts: number;
  p: number;
  gd: number;
  gf: number;
  ga: number;
  expPts: number | null;
  expGd: number | null;
  title: number | null;
  cl: number | null;
  relegated: number | null;
  playoff: number | null;
};

export function site() {
  return siteJson as unknown as Site;
}
export function fixtures() {
  return fixturesJson as unknown as Fixture[];
}
export function upcoming() {
  return upcomingJson as unknown as MatchOdds[];
}
export function pairs() {
  return pairsJson as unknown as MatchOdds[];
}
export function incidents() {
  return incidentsJson as unknown as Incident[];
}
export function varMatches() {
  return varMatchesJson as unknown as VarMatch[];
}
export function highlights() {
  return highlightsJson as unknown as Record<string, { videoId: string; title: string | null }>;
}
export function players() {
  return playersJson as unknown as Player[];
}
export function values() {
  return valuesJson as unknown as ValueRow[];
}
export function scout() {
  return scoutJson as unknown as Scout[];
}
export function teamState() {
  return stateJson as unknown as TeamState[];
}
export function tables() {
  return tablesJson as unknown as Record<string, { simulated: boolean; rows: TableRow[] }>;
}

export function teamsIn(league: string) {
  return site()
    .teams.filter((t) => t.league === league)
    .sort((a, b) => a.team.localeCompare(b.team));
}

export function club(name: string) {
  return site().teams.find((t) => t.team === name);
}

export function resolveLeague(sp: Record<string, string | string[] | undefined>) {
  const leagues = site().leagues;
  const asked = one(sp, "league");
  if (asked && asked in leagues) return asked;
  for (const key of ["home", "away", "team"]) {
    const name = one(sp, key);
    const row = name ? club(name) : undefined;
    if (row) return row.league;
  }
  return "EPL";
}

export function playerByLabel(label: string | undefined) {
  if (!label) return undefined;
  return players().find((p) => p.label === label);
}

export function formOf(league: string, team: string) {
  const rows = fixtures()
    .filter((f) => f.league === league && f.finished && (f.home === team || f.away === team) && f.hg != null && f.ag != null)
    .sort((a, b) => (a.kickoff < b.kickoff ? 1 : -1))
    .slice(0, 5)
    .reverse();
  return rows.map((f) => {
    const gf = f.home === team ? f.hg! : f.ag!;
    const ga = f.home === team ? f.ag! : f.hg!;
    const result = gf > ga ? "W" : gf === ga ? "D" : "L";
    const opp = f.home === team ? f.away : f.home;
    return { result, opp, score: `${f.hg}–${f.ag}`, kickoff: f.kickoff };
  });
}
