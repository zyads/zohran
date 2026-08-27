<h1 align="center">Where the city quietly gives up.</h1>

<p align="center">
<b>Open-source civic tools for New York City, built on nothing but public data.</b><br>
No accounts. No tracking. No city access needed. Rebuilt every night.<br><br>
<a href="https://zyadshehadeh.dev/zohran/"><b>zyadshehadeh.dev/zohran</b></a>
</p>

---

Every 311 request ends with a one-line resolution. A lot of them say some version of
*"we looked, we didn't see it, closed."* The city publishes closure rates and time-to-close.
It does not publish **how often "closed" meant nothing happened** — or how often the same
address had to report the same problem again.

So we counted. Over the last 90 days:

| | |
|---|---|
| **51%** | of all 311 closures citywide were closed without visible action |
| **80%** | for the Department of Buildings · **62%** HPD · **59%** NYPD (median 1.4 h to close) |
| **46%** | of closed complaints were re-reported from the same address within 30 days |
| **73%** | of blocked-bike-lane complaints ended with no action, median ~1 hour |
| **+20%** | heat & hot-water violations this season vs last (52,121 vs 43,581) |

Every number above links to a page where you can look up your own block.

## The tools

| | What it does | Data |
|---|---|---|
| [**311 Ghost Tracker**](https://zyadshehadeh.dev/zohran/ghost-tracker/) | Every agency and community board scored on *closed-without-action* rate and *re-report* rate. Find your board. | 311 (`erm2-nwe9`) |
| [**Re-Report**](https://zyadshehadeh.dev/zohran/rereport/) | Paste a 311 number or address → full history for that location → a new report that carries the receipts. Runs entirely in your browser. | 311, live |
| [**Heat & Hot Water**](https://zyadshehadeh.dev/zohran/heat/) | Buildings and landlords ranked by heat violations, per community district, this season vs last. Check an address before you sign. | HPD violations + registrations, 311 |
| [**Lane Blockage Map**](https://zyadshehadeh.dev/zohran/lanes/) | Where bike lanes get blocked, how often those complaints go nowhere, and the slowest bus segments in the city. | 311, MTA segment speeds |
| [**Parks**](https://zyadshehadeh.dev/zohran/parks/) | Every park ranked by open complaints, what gets fixed, what gets closed without a fix, and how long it takes. | 311 (DPR) |

## How it's built

One Python script per tool pulls from [NYC Open Data](https://opendata.cityofnewyork.us/), writes one `data.json`,
and one static HTML page renders it. No framework, no build step, no server, no CDN JavaScript.
GitHub Actions rebuilds the data nightly and deploys to Pages. You can run the whole thing from a laptop:

```sh
git clone https://github.com/zyads/zohran && cd zohran
make          # builds every tool's data.json → dist/
make serve    # http://localhost:8090
```

Each tool's `README.md` documents its methodology; the scoring rules (the exact phrases that count as
"closed without action", the 30-day re-report window, the heat-season boundaries) are at the top of each
`build.py`, and repeated in plain language on every page. If you think a rule is wrong, open an issue —
that's the point of publishing them.

## Principles

- **Public data only.** If the city doesn't publish it, we don't use it.
- **Nothing stored.** No analytics, no accounts, no server that sees what you look up.
- **Reproducible.** Every number on every page can be regenerated with `make`.
- **Forkable.** MIT. Point it at another city's Socrata portal and most of it just works.

## Contributing

Ideas that fit: new scoring lenses on existing data, other agencies, other cities.
Ideas that don't: anything requiring accounts, scraping private platforms, or non-public data.

<p align="center"><sub>Built in New York · MIT License</sub></p>
