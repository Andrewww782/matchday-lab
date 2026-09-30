# FootyMinds feature roadmap
| # | Release | Contents |
|---|---|---|
| 1 ✅ | **Top 5 leagues** (shipped) | this plan (below), plus refresh-failure alerts |
| 2 ✅ | **Scorelines** (shipped) | goals model (Dixon-Coles): most likely score, both teams to score, over 2.5 goals; better goal-difference tiebreaks in the simulator |
| 2½ ✅ | **Colour & motion** (shipped) | league colours (banner, accents, heatmaps), club-colour stripes, heading font; entrances, growing bars, count-ups, hover lifts, "soon" pulse; all off under reduced motion |
| 3 ✅ | **Fan VAR** (shipped, the headline act) | every penalty, red card, VAR check and ruled-out goal in the top 5 leagues from ESPN commentary (daily); anonymous one-per-device votes (Neon Postgres), fan flags from set choices, fans-vs-neutrals split, referee report card, "Who gets robbed?", embedded official highlights; Fantasy parked |
| 3½ ✅ | **Offside check** (shipped) | draw the lines yourself on any screenshot: YOLOX player detection (ONNX, Apache-2.0), click attacker + defender, two lines parallel to the goal line give the vanishing point → OFFSIDE / ONSIDE; optional 4 box corners → centimetres, top-down map, 3D VAR view; linked from Fan VAR goal calls and saved as your vote |
| 4 | **Profile pages** | player profile (becomes the search destination) and team page (form, xG trend, fixtures, squad values, season odds, Fan VAR record) |
| 5 | **Smarter predictions** | injury-aware team strength ("Palmer out: −6%"), predicted line-ups, in-season retraining, separate goalkeeper value model |
| 6 | **New pages** | gameweek review (hits, misses, upsets, xG over/under-performers); transfer-window mode |
| 7 | **Sharing** | shareable image cards, share buttons, simple usage analytics |
| 8 | **Engagement** | fans-vs-the-model leaderboard; weekly email/post (needs an account/database decision at that point) |
| 9 | **Housekeeping** | automatic season rollover, open-sourcing, fresher market-value source |
| later | **Fantasy (parked)** | the FPL page is hidden but still builds; bring it back with the planned upgrades (multi-transfer planner with −4 hits, chip advisor, best XI under £100m, mini-league view, price changes) |
| 10 ✅ | **Redesign** (shipped, pulled forward) | Krackerz-inspired look (docs/redesign-plan.md): cream paper, chunky type + script accents, red/maroon blocks, lime stickers, top menu; hosting, no-sleep and custom-domain decisions still open |

---

