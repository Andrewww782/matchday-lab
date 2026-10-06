"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type Row = { label: string; name: string; team: string; league: string; pos: string };

export function Finder({ players }: { players: Row[] }) {
  const [query, setQuery] = useState("");
  const hits = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q.length < 2) return [];
    return players.filter((row) => row.label.toLowerCase().includes(q)).slice(0, 12);
  }, [players, query]);

  return (
    <div>
      <label>
        Name
        <input
          type="search"
          value={query}
          placeholder="Saka, Yamal, Kane…"
          onChange={(event) => setQuery(event.target.value)}
          autoFocus
        />
      </label>
      <div className="links" style={{ marginTop: "0.8rem" }}>
        {hits.map((row) => (
          <Link key={row.label} href={`/player?player=${encodeURIComponent(row.label)}`}>
            <strong>{row.name}</strong>
            {row.team} · {row.league} · {row.pos}
          </Link>
        ))}
      </div>
      {query.trim().length >= 2 && hits.length === 0 ? <p className="note">No player matches that.</p> : null}
    </div>
  );
}
