# Parks

A per-park scoreboard from NYC 311: which parks have the most open complaints, which
complaint types get closed without action, and how long fixes take.

- `build.py` pulls the last 180 days of 311 requests handled by the Parks Department
  (`agency='DPR'`, dataset `erm2-nwe9`) one day at a time, reusing the fetch strategy and
  closed-without-action heuristic from `../ghost-tracker/build.py`, and writes `site/data.json`.
- Park names come from `park_facility_name` when set, otherwise (since 2025 that is almost
  never) from the incident address of requests whose location type is "Park".
- The borough outline is copied from `../lanes/site/data.json` at build time, so build lanes first.

```
python3 build.py            # ~2 min, no API token needed
python3 -m http.server -d site
```
