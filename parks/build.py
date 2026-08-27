#!/usr/bin/env python3
"""Parks — build step.

Pulls the last N days of NYC 311 requests handled by the Department of Parks and
Recreation (Socrata dataset erm2-nwe9, agency = DPR), scores every named park
facility on open complaints, closed-without-action rate and time to close, and
writes site/data.json for the static page.

Reuses the per-day fetch strategy and the closed-without-action heuristic from
../ghost-tracker/build.py (imported, not copied). The borough outline is copied
from ../lanes/site/data.json at build time.

Dependencies: Python 3.8+ and `requests`. No app token required.

Usage:  python3 build.py [--days 180] [--out site/data.json]
"""
import argparse
import importlib.util
import json
import re
import os
import statistics
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Import the ghost-tracker module by path (its directory name has a hyphen).
_spec = importlib.util.spec_from_file_location("ghost_build", os.path.join(ROOT, "ghost-tracker", "build.py"))
gt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gt)
is_ghost, parse_ts = gt.is_ghost, gt.parse_ts

API = gt.API
FIELDS = [
    "unique_key", "created_date", "closed_date", "status", "complaint_type",
    "descriptor", "park_facility_name", "park_borough", "borough",
    "location_type", "incident_address", "landmark",
    "resolution_description", "latitude", "longitude",
]
UNNAMED = {"", "unspecified", "n/a", "none", "unknown"}


def fetch(days, page_size=50000, log=print):
    """Per-day fetch like ghost-tracker, filtered to agency = DPR."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    s = requests.Session()
    s.headers["User-Agent"] = "zohran-parks/1.0 (+https://github.com/zyads/zohran)"
    tok = os.environ.get("SOCRATA_APP_TOKEN")
    if tok:
        s.headers["X-App-Token"] = tok

    def get(params):
        for attempt in range(8):
            try:
                r = s.get(API, params=params, timeout=120)
                if r.status_code == 429 or r.status_code >= 500:
                    wait = min(60, 2 ** attempt * 3)
                    log(f"  HTTP {r.status_code}, retrying in {wait}s"); time.sleep(wait); continue
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError) as e:
                wait = min(60, 2 ** attempt * 3)
                log(f"  {e!r}, retrying in {wait}s"); time.sleep(wait)
        raise SystemExit("gave up fetching from Socrata")

    rows, day = [], start
    while day < now:
        nxt = day + timedelta(days=1)
        where = (f"agency='DPR' AND created_date >= '{day:%Y-%m-%dT%H:%M:%S}' "
                 f"AND created_date < '{nxt:%Y-%m-%dT%H:%M:%S}'")
        offset = 0
        while True:
            page = get({"$select": ",".join(FIELDS), "$where": where, "$limit": page_size, "$offset": offset})
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        if day.day == 1 or nxt >= now:
            log(f"  {day:%Y-%m-%d}: {len(rows):,} rows so far")
        day = nxt
    return rows, start.strftime("%Y-%m-%d")


def titlecase(s):
    """Title-case a park name without mangling apostrophes ("OWL'S HEAD" -> "Owl's Head")."""
    return re.sub(r"[A-Za-z]+(?:'[A-Za-z]+)?", lambda m: m.group(0).capitalize(), s)


def park_name(r):
    """The park a request is about, or "" if it is not about a park.

    311 has a park_facility_name field, but since 2025 it is "Unspecified" on
    more than 99% of DPR requests. When the request's location type is "Park",
    the park's name is instead recorded as the incident address / landmark
    (e.g. "BAISLEY POND PARK"), so fall back to that when it is not a street
    address. Street-tree requests (location type "Street") are not parks.
    """
    n = (r.get("park_facility_name") or "").strip()
    if n.lower() not in UNNAMED:
        return titlecase(n) if n.isupper() else n
    if (r.get("location_type") or "").strip().lower() != "park":
        return ""
    a = (r.get("incident_address") or r.get("landmark") or "").strip()
    if not a or a[0].isdigit() or a.lower() in UNNAMED:
        return ""
    return titlecase(a)


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def median(vals, nd=1):
    return round(statistics.median(vals), nd) if vals else None


def summarise(lst):
    closed = [x for x in lst if x["closed"]]
    ghost = [x for x in closed if x["ghost"]]
    days = [x["days"] for x in closed if x["days"] is not None]
    return {"total": len(lst), "open": len(lst) - len(closed), "closed": len(closed),
            "ghost": len(ghost), "ghost_pct": pct(len(ghost), len(closed)),
            "median_days": median(days)}


def build(rows, since, days):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recs = []
    for r in rows:
        created = parse_ts(r.get("created_date"))
        if not created:
            continue
        closed = parse_ts(r.get("closed_date"))
        is_closed = (r.get("status") or "").strip().lower() == "closed" and closed is not None
        d = (closed - created).total_seconds() / 86400.0 if is_closed and closed >= created else None
        park = park_name(r)
        boro = (r.get("park_borough") or r.get("borough") or "").strip().title()
        try:
            lat, lon = float(r.get("latitude")), float(r.get("longitude"))
        except (TypeError, ValueError):
            lat = lon = None
        recs.append({"park": park, "in_park": (r.get("location_type") or "").strip().lower() == "park",
                     "boro": boro or "Unspecified",
                     "ctype": (r.get("complaint_type") or "Unknown").strip(),
                     "desc": (r.get("descriptor") or "Unspecified").strip(),
                     "created": created, "closed": closed if is_closed else None, "days": d,
                     "ghost": is_closed and is_ghost(r.get("resolution_description")),
                     "lat": lat, "lon": lon})

    # ---- per park
    by_park = defaultdict(list)
    for x in recs:
        if x["park"].lower() not in UNNAMED:
            by_park[(x["park"], x["boro"])].append(x)
    parks = []
    for (name, boro), lst in by_park.items():
        s = summarise(lst)
        descs = defaultdict(int)
        for x in lst:
            descs[x["desc"]] += 1
        pts = [(x["lat"], x["lon"]) for x in lst if x["lat"] is not None]
        s.update({"name": name, "borough": boro,
                  "top": [k for k, _ in sorted(descs.items(), key=lambda kv: -kv[1])[:3]],
                  "lat": round(sum(p[0] for p in pts) / len(pts), 4) if pts else None,
                  "lon": round(sum(p[1] for p in pts) / len(pts), 4) if pts else None})
        parks.append(s)
    parks.sort(key=lambda s: (-s["open"], -s["total"]))
    top_open = parks[:50]
    top_ghost = sorted([p for p in parks if p["total"] >= 10 and p["ghost_pct"] is not None],
                       key=lambda s: (-s["ghost_pct"], -s["total"]))[:50]
    # compact list for the map + search: every park with a centroid
    all_parks = [{"name": p["name"], "borough": p["borough"], "total": p["total"], "open": p["open"],
                  "ghost_pct": p["ghost_pct"], "median_days": p["median_days"], "top": p["top"],
                  "lat": p["lat"], "lon": p["lon"]} for p in parks]

    # ---- boroughs
    by_boro = defaultdict(list)
    for x in recs:
        by_boro[x["boro"]].append(x)
    boroughs = {}
    for b, lst in by_boro.items():
        boroughs[b] = summarise(lst)
        boroughs[b]["in_park"] = summarise([x for x in lst if x["in_park"]])

    # ---- complaint types + descriptors citywide
    # Complaint types over all DPR requests; descriptors only for requests
    # located in a park (the street-tree descriptors are not park problems).
    by_ct, by_desc = defaultdict(list), defaultdict(list)
    for x in recs:
        by_ct[x["ctype"]].append(x)
        if x["in_park"]:
            by_desc[(x["ctype"], x["desc"])].append(x)
    ctypes = []
    for ct, lst in by_ct.items():
        s = summarise(lst); s["complaint_type"] = ct; ctypes.append(s)
    ctypes.sort(key=lambda s: -s["total"])
    descs = []
    for (ct, de), lst in by_desc.items():
        if len(lst) < 30:
            continue
        s = summarise(lst); s.update({"complaint_type": ct, "descriptor": de}); descs.append(s)
    descs.sort(key=lambda s: -s["total"])

    # ---- weekly created vs closed, in-park requests only (closes by close week)
    def week(dt):
        return (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
    wk_c, wk_x = defaultdict(int), defaultdict(int)
    since_dt = datetime.strptime(since, "%Y-%m-%d")
    for x in recs:
        if not x["in_park"]:
            continue
        wk_c[week(x["created"])] += 1
        if x["closed"] and x["closed"] >= since_dt:
            wk_x[week(x["closed"])] += 1
    weeks = sorted(set(wk_c) | set(wk_x))
    weekly = [{"week": w, "created": wk_c.get(w, 0), "closed": wk_x.get(w, 0)} for w in weeks]

    # ---- borough outline from lanes
    outline = []
    try:
        with open(os.path.join(ROOT, "lanes", "site", "data.json")) as f:
            outline = json.load(f).get("borough_outline", [])
    except (OSError, ValueError):
        print("  (no lanes/site/data.json; map outline omitted)")

    city = summarise(recs)
    city["named_parks"] = len(parks)
    in_park = summarise([x for x in recs if x["in_park"]])
    in_park["named"] = sum(1 for x in recs if x["park"])
    return {
        "generated_at": now.replace(tzinfo=timezone.utc).isoformat(timespec="seconds"),
        "window_days": days, "window_start": since,
        "citywide": city, "in_park": in_park, "boroughs": boroughs,
        "top_open": top_open, "top_ghost": top_ghost, "parks": all_parks,
        "complaint_types": ctypes, "descriptors": descs, "weekly": weekly,
        "borough_outline": outline,
        "heuristic": {"ghost_patterns": gt.GHOST_PATTERNS, "action_patterns": gt.ACTION_PATTERNS},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--out", default=os.path.join(HERE, "site", "data.json"))
    ap.add_argument("--cache", help="read/write raw rows here instead of refetching (dev only)")
    a = ap.parse_args()
    if a.cache and os.path.exists(a.cache):
        with open(a.cache) as f:
            rows, since = json.load(f)
        print(f"Loaded {len(rows):,} cached rows")
    else:
        print(f"Fetching last {a.days} days of DPR 311 requests ...")
        rows, since = fetch(a.days)
        if a.cache:
            with open(a.cache, "w") as f:
                json.dump([rows, since], f)
    print(f"Scoring {len(rows):,} requests ...")
    data = build(rows, since, a.days)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    c = data["citywide"]
    print(f"Wrote {a.out} ({os.path.getsize(a.out)/1024:.0f} KB)")
    ip = data["in_park"]
    print(f"  in-park (location type Park): total {ip['total']:,}  open {ip['open']:,}  ghost {ip['ghost_pct']}%  median days {ip['median_days']}  named {ip['named']:,}")
    print(f"  all DPR: total {c['total']:,}  open {c['open']:,}  closed {c['closed']:,}  "
          f"closed-without-action {c['ghost']:,} ({c['ghost_pct']}% of closed)  median days {c['median_days']}  "
          f"named parks {c['named_parks']:,}")
    for b, s in sorted(data["boroughs"].items(), key=lambda kv: -kv[1]["total"]):
        print(f"  {b:15s} total {s['total']:6,} open {s['open']:5,} ghost {s['ghost_pct']}%")
    print("  top open:", [(p["name"], p["open"]) for p in data["top_open"][:5]])
    print("  top ghost:", [(p["name"], p["ghost_pct"], p["total"]) for p in data["top_ghost"][:5]])
    print("  types:", [(t["complaint_type"], t["total"], t["ghost_pct"], t["median_days"]) for t in data["complaint_types"][:8]])


if __name__ == "__main__":
    main()
