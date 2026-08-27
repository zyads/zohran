# Heat & Hot Water Scoreboard

Which NYC buildings and landlords failed to provide heat or hot water last winter —
ranked per community district and citywide, with an address lookup. Static site, no
server, no tracking.

**Why this and not Who Owns What?** [JustFix's Who Owns What](https://whoownswhat.justfix.org)
is the best tool for *one* building or *one* landlord's portfolio; this tool answers the
other question — "who are the worst heat landlords in my district this season?" — and
links every building straight to Who Owns What and HPD Online for the deep dive.

## Build

```
pip install requests
python3 build.py          # ~5 min, writes site/data.json (~3 MB)
python3 -m http.server -d site
```

Optional: `SODA_APP_TOKEN=...` for a higher NYC Open Data rate limit.

## What it counts

- **Heat violations**: HPD violations (`wvxf-dwi5`) whose notice text mentions HEAT or
  HOT WATER, by notice-issued date, per heating season (Oct 1 – May 31).
- **311 heat complaints**: 311 requests (`erm2-nwe9`) with complaint type `HEAT/HOT WATER`.
- **Landlord**: the head officer named on the building's current HPD registration
  (`tesw-yqqr` + `feu5-w2e2`); falls back to individual/corporate owner. Landlords who
  register different people or LLCs per building will be split across several names —
  Who Owns What does this de-duplication far better.
- Buildings with no violations and fewer than two complaints are dropped to keep the
  data small.

## Credits

Data: [NYC Open Data](https://opendata.cityofnewyork.us/) (HPD, 311). Inspired by and
linking to [JustFix](https://www.justfix.org) — Who Owns What and the open-source
[nycdb](https://github.com/nycdb/nycdb). MIT.
