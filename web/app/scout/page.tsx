import type { Metadata } from "next";
import Link from "next/link";
import { ClubName } from "@/components/Bits";
import { playerByLabel, players, scout, site } from "@/lib/data";
import { href, money } from "@/lib/format";
import { lookalikes } from "@/lib/similar";

export const metadata: Metadata = { title: "Who plays like him?" };

export default async function ScoutPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const picked = playerByLabel(typeof sp.player === "string" ? sp.player : undefined);
  const all = scout();
  const me = picked ? all.find((row) => row.pid === picked.pid) : undefined;
  const meta = site().scoutMeta;
  const cols = me ? (me.pos === "GK" ? meta.styleStats.GK : meta.attStats[me.pos] ?? []) : [];
  const hits = me ? lookalikes(all, me.pid, cols, me.pos === "GK" ? "EPL" : null) : [];

  return (
    <>
      <h1>
        Who plays <em>like him?</em>
      </h1>
      <p className="lede">
        Similar players anywhere in the top five, from what they do per 90 minutes. Same position, other clubs.
        {meta.minMinutes ? ` At least ${meta.minMinutes} minutes since last season.` : ""}
      </p>
      {!me ? (
        <p className="note">
          <Link href="/find">Find a player</Link> to start. Goalkeepers are Premier League only, because that is where the save numbers come from.
        </p>
      ) : (
        <>
          <article className="card">
            <h2 style={{ textTransform: "none", fontFamily: "DM Sans, sans-serif" }}>{me.name}</h2>
            <p>
              <ClubName name={me.team} /> · {me.pos} · {me.style}
            </p>
          </article>
          <div className="eyebrow">Look-alikes</div>
          <h2>Most similar to {me.web || me.name}</h2>
          <div className="links">
            {hits.map((hit) => (
              <Link key={hit.player.pid} href={href("/player", { player: players().find((row) => row.pid === hit.player.pid)?.label })}>
                <strong>
                  {hit.player.name} · {hit.similarity.toFixed(0)}% similar
                </strong>
                {hit.player.team} · {hit.player.leagueName} · {hit.player.style} · {money(hit.player.value)}
              </Link>
            ))}
          </div>
          {hits.length === 0 ? <p className="note">No look-alikes with enough minutes.</p> : null}
        </>
      )}
    </>
  );
}
