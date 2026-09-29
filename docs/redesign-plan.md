# FootyMinds redesign plan ("Matchday Dark"), parked until the feature roadmap is done

**Groundwork already in place (colour & motion pass):** `app/theme.py` (league palettes, fixed meanings, chart helpers), the self-hosted Barlow Condensed heading font, the stylesheet + motion script in `app/ui.py` / `app/motion.js`. Build on these rather than starting over.

**Direction chosen:** "Matchday Dark", with a top bar replacing the sidebar: Home · Matches (Predictions · Season odds · Track record) · Players (Value · Similar · Compare) · Fantasy (Top picks · My team · Fixtures). About goes in the footer. Old URLs keep working.

**Principles:**
- One question per screen, answered above the fold.
- At most 3 big numbers visible.
- Everything pre-filled.
- Fixed colour meanings: green = home / good, blue = away, grey = draw, amber = caution, red = bad. Colour is never the only signal.
- Plain English first.
- Tap targets ≥ 44 px.

**Tokens (dark):**
| Token | Hex | Token | Hex |
|---|---|---|---|
| bg | #0A0F0C | accent | #2BE07F |
| surface | #111814 | accent-dim | #1A8F52 |
| surface-2 | #18221C | away | #4C8DFF |
| border | #223029 | draw | #5E6E66 |
| text | #EAF2ED | amber | #FFB224 |
| muted | #8DA397 | red | #FF5C5C |

There is also a light variant. All text meets WCAG AA.

**Type:**
- Barlow Condensed 700/800 for headings; Inter for body, with tabular numbers. Both self-hosted, SIL Open Font License.
- Sizes: title 40/32 px (desktop/phone), section 22 px, body 15 px, caption 13 px, stat numbers 36 px.

**Shape:** 12 px card radius, 8-pt spacing grid, 1 px borders instead of shadows.

**Brand:**
- Wordmark: FOOTY (white) and MINDS (green), with a small football/brain mark as the favicon.
- Clubs shown as a colour dot + 3-letter code; players as an initials avatar with a club-colour ring. No crests or photos.

**Components:** fixture card, matchup header, stat tile, verdict chip, player header, restyled "Why?" bars, W/D/L form pills, player card, tug-of-war stat rows (Compare), Out → In transfer cards, and friendly empty/error states.

**Pages:**
- **Home:** gameweek hero with a big search box; 3 stat tiles (title favourite · best bargain · captain pick); match of the week; fixture card grid.
- **Predictions:** matchup header, big odds bar, verdict, form pills, "Why?".
- **Season odds:** chip-style table, heatmap, and what-if as Home/Draw/Away toggles per fixture.
- **Value:** a value meter (market vs stats marker line); Bargains and Pricey as card rows.
- **Similar:** player card grid.
- **Compare:** tug-of-war rows grouped Attacking / Creating / Defending.
- **Fantasy:** split into Top picks, My team and Fixtures.

**Implementation (Streamlit 1.64 supports it):**
- `config.toml` theme: `base=dark`, `fontFaces`, `headingFont`, chart palettes, border colours, `[theme.light]`, `enableStaticServing`.
- `static/` for fonts and logo.
- `app/theme.py` for tokens and the Plotly template.
- `app/ui.py` as the component library.
- `st.navigation(position="top")` with sections.
- Pages regrouped into `matches/`, `players/`, `fantasy/`.
- The pipeline is untouched.

About 4 days. The same tokens and components carry over to a Next.js rebuild if you choose that later.

**Verification:** updated AppTests; Playwright screenshots in dark and light at 1400 px and 390 px; contrast check; keyboard pass; live check.
