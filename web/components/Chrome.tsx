"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TOP = [
  { href: "/", label: "This week" },
  { href: "/var", label: "Fan VAR" },
];

const MATCHES = [
  { href: "/match", label: "Who wins?" },
  { href: "/team", label: "Club profile" },
  { href: "/table", label: "Season odds" },
  { href: "/offside", label: "Offside check" },
];

const PLAYERS = [
  { href: "/find", label: "Find a player" },
  { href: "/player", label: "Player profile" },
  { href: "/value", label: "What's he worth?" },
  { href: "/scout", label: "Who plays like him?" },
  { href: "/compare", label: "Head-to-head" },
];

function Item({ href, label }: { href: string; label: string }) {
  const path = usePathname();
  const on = href === "/" ? path === "/" : path === href;
  return (
    <Link href={href} className={on ? "on" : undefined}>
      {label}
    </Link>
  );
}

export function Nav() {
  const path = usePathname();
  const matchesOn = MATCHES.some((item) => item.href === path);
  const playersOn = PLAYERS.some((item) => item.href === path);
  return (
    <nav className="nav" aria-label="Pages">
      {TOP.map((item) => (
        <Item key={item.href} {...item} />
      ))}
      <details className="menu">
        <summary className={matchesOn ? "on" : undefined}>Matches</summary>
        <div className="menu-pop">
          {MATCHES.map((item) => (
            <Item key={item.href} {...item} />
          ))}
        </div>
      </details>
      <details className="menu">
        <summary className={playersOn ? "on" : undefined}>Players</summary>
        <div className="menu-pop">
          {PLAYERS.map((item) => (
            <Item key={item.href} {...item} />
          ))}
        </div>
      </details>
      <Item href="/about" label="How it works" />
    </nav>
  );
}
