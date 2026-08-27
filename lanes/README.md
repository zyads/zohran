# Lane Blockage Map

Static map + tables of NYC 311 "Blocked Bike Lane" reports (last 180 days, gridded to
~110 m cells, with closed-without-action rate) and the slowest MTA bus route segments
for the latest published month. Public data only, no tile server, no CDNs.

```
pip install requests
python3 lanes/build.py            # writes lanes/site/data.json (~120 KB)
python3 -m http.server -d lanes/site 8000   # open http://localhost:8000
```

Sources: 311 `erm2-nwe9` (data.cityofnewyork.us), MTA Bus Route Segment Speeds
`kufs-yh3x` (data.ny.gov), Borough Boundaries `gthc-hcne`. An optional
`SOCRATA_APP_TOKEN` env var raises the API rate limit.

Caveats: 311 has no "blocked bus lane" descriptor, so bus lanes are only seen through
speeds. "Closed without action" is a resolution-text heuristic (patterns in `build.py`).
Slow segments include terminals and dwell time.
