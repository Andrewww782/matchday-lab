import type { Scout } from "./data";

export function lookalikes(all: Scout[], pid: number, cols: string[], league: string | null) {
  const me = all.find((p) => p.pid === pid);
  if (!me || cols.length === 0) return [];
  let pool = all.filter((p) => p.pos === me.pos);
  if (league) pool = pool.filter((p) => p.league === league || p.pid === pid);
  pool = pool.filter((p) => cols.every((c) => p.p90[c] != null));
  if (pool.length < 2) return [];

  const matrix = pool.map((p) => cols.map((c) => p.p90[c] as number));
  const mean = cols.map((_, j) => matrix.reduce((sum, row) => sum + row[j], 0) / matrix.length);
  const sd = cols.map((_, j) => {
    const variance = matrix.reduce((sum, row) => sum + (row[j] - mean[j]) ** 2, 0) / matrix.length;
    return Math.sqrt(variance) || 1e-9;
  });
  const z = matrix.map((row) => row.map((value, j) => (value - mean[j]) / sd[j]));
  const mine = pool.findIndex((p) => p.pid === pid);
  const vector = z[mine];
  const norm = Math.hypot(...vector) || 1e-9;

  return pool
    .map((player, index) => {
      const dot = z[index].reduce((sum, value, j) => sum + value * vector[j], 0);
      const cosine = dot / ((Math.hypot(...z[index]) || 1e-9) * norm);
      return { player, similarity: Math.max(0, Math.min(1, cosine)) * 100 };
    })
    .filter((row) => row.player.pid !== pid && row.player.team !== me.team)
    .sort((a, b) => b.similarity - a.similarity)
    .slice(0, 8);
}
