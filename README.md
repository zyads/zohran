# zohran — civic tools for NYC, built on public data

Open-source, local-first tools that help New Yorkers get things fixed. Built to be
useful **whether or not** anyone in City Hall ever replies. Everything runs on NYC Open
Data / public APIs — no city access, no insider data, no permission needed.

## Ideas, ranked by "actually helps NYC" (not by demo-wow)

### 1. 311 Ghost Tracker  ← ship this first
NYC 311 "closes" complaints constantly without fixing them ("condition not observed",
"referred to other agency"). Nobody aggregates that. Tool: pull the public 311 dataset,
score every agency + community district by **closed-without-action rate** and
**re-report rate** (same address, same problem, reopened within 30 days). Public
leaderboard, per-block lookup, weekly diff. Shows where the system quietly gives up — pure public data.
- Data: `data.cityofnewyork.us/resource/erm2-nwe9.json` (311, live)
- Stack: one Python cron → SQLite → static site. Zero servers to babysit.

### 2. Re-Report Bot (for residents, not the office)
One-tap page: paste an old 311 number → it checks status, and if it was closed
without a fix, pre-fills a *new* 311 complaint with the history attached
("3rd report, prev SR#s: …"). Turns individual frustration into a paper trail.
Runs entirely client-side.

### 3. Landlord Heat & Hot Water Scoreboard
Winter matters. Join HPD violations + 311 heat complaints + DOB → per-building and
per-landlord (via HPD registration) heat/hot-water violation history. Tenants punch in
an address before signing a lease; organizers see the worst 50 landlords per district.
This directly feeds tenant-protection work.
- Data: HPD violations `wvxf-dwi5`, HPD registrations `tesw-yqqr`, 311.

### 4. Bus Lane / Bike Lane Blockage Heatmap
MTA bus speeds (public) + 311 "blocked bike lane" + ACE camera enforcement data →
where buses are slowest and why. Cheap, visual, matches the transit agenda.

## Principles
Public data only · static-first, no accounts · everything reproducible from a
`make` · MIT licensed · no analytics, no tracking.
