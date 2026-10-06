import type { Metadata } from "next";
import { Finder } from "@/components/Finder";
import { players } from "@/lib/data";

export const metadata: Metadata = { title: "Find a player" };

export default function FindPage() {
  const list = players().map((row) => ({
    label: row.label,
    name: row.name,
    team: row.team,
    league: row.leagueName,
    pos: row.pos,
  }));
  return (
    <>
      <h1>
        Find a <em>player</em>
      </h1>
      <p className="lede">Search anyone who has played in Europe&apos;s top five leagues this season or last.</p>
      <Finder players={list} />
    </>
  );
}
