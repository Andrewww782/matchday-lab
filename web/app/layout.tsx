import type { Metadata } from "next";
import Link from "next/link";
import { Nav } from "@/components/Chrome";
import { site } from "@/lib/data";
import { STREAMLIT } from "@/lib/format";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "FootyMinds", template: "%s · FootyMinds" },
  description: "Fan VAR, match predictions and player values for Europe's top five leagues.",
  icons: { icon: "/ball.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const info = site();
  const when = info.updatedAt
    ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(info.updatedAt))
    : null;
  return (
    <html lang="en">
      <body>
        <div className="wrap top">
          <Link href="/" className="brand">
            <img src="/ball.png" alt="" width={36} height={36} />
            <span>
              FOOTY<em>Minds</em>
            </span>
          </Link>
          <Nav />
          <a className="streamlit-link" href={STREAMLIT}>
            Streamlit app
          </a>
        </div>
        <main className="wrap">{children}</main>
        <footer className="footer">
          <div className="wrap">
            <div className="w">
              Footy<b>Minds</b>
            </div>
            <p>
              {info.season ? `${info.season} · ` : ""}
              Premier League, La Liga, Serie A, Bundesliga, Ligue 1
              {when ? ` · data updated ${when}` : ""}
            </p>
            <p>Data: Understat, football-data.co.uk, Fantasy Premier League and Transfermarkt.</p>
            <p>Match events: ESPN. Highlights: official league channels on YouTube.</p>
            <p>
              The original app stays at <a href={STREAMLIT}>footyminds.streamlit.app</a>. Not affiliated with any league, club or FPL. For fun, not betting advice.
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
