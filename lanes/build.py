#!/usr/bin/env python3
"""Lane Blockage Map — build script.

Pulls (1) NYC 311 "Blocked Bike Lane" complaints for the last 180 days and
(2) the latest month of MTA bus route-segment speeds, plus a simplified borough
outline, and writes site/data.json for the static page in site/.

Only stdlib + requests. Re-runnable; no state kept between runs.
"""
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "site", "data.json")

NYC_311 = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
BORO = "https://data.cityofnewyork.us/resource/gthc-hcne.json"
MTA_SPEEDS = "https://data.ny.gov/resource/kufs-yh3x.json"   # Bus Route Segment Speeds: Beginning 2025

DAYS = 180
# 311 has no "blocked bus lane" descriptor (verified 2026-08 via $group=descriptor);
# bike-lane blockage is the only lane-blockage complaint type that exists.
DESCRIPTORS = ["Blocked Bike Lane"]
GRID = 3            # decimal places of lat/lon -> ~110 m x ~85 m cells
TOP_CELLS = 500
TOP_SEGMENTS = 50
MIN_TRIPS = 200     # a segment needs this many observed bus trips in the month to be ranked

HEADERS = {}
if os.environ.get("SOCRATA_APP_TOKEN"):
    HEADERS["X-App-Token"] = os.environ["SOCRATA_APP_TOKEN"]


def get(url, params, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=120)
            if r.status_code == 200:
                return r.json()
            print(f"  HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  request error: {e}", file=sys.stderr)
        time.sleep(2 * (i + 1))
    raise SystemExit(f"giving up on {url}")


def paged(url, params, page=50000):
    off = 0
    while True:
        rows = get(url, {**params, "$limit": page, "$offset": off})
        yield from rows
        if len(rows) < page:
            return
        off += page


# ---------------------------------------------------------------- 311 -------
NO_ACTION = re.compile(
    r"observed no|no evidence|not observed|no violation|unable to|referred|"
    r"could not|duplicate|not necessary|does not fall under|no action",
    re.I,
)
ACTION = re.compile(r"summons|corrected|arrest|report was prepared|towed", re.I)


def classify(status, res):
    """closed-without-action / action / open / other"""
    if status and status.lower() not in ("closed",):
        return "open"
    res = res or ""
    if ACTION.search(res):
        return "action"
    if NO_ACTION.search(res):
        return "no_action"
    return "other"


def fetch_311():
    since = (datetime.now(timezone.utc) - timedelta(days=DAYS)).strftime("%Y-%m-%dT00:00:00")
    desc = ",".join("'" + d.replace("'", "''") + "'" for d in DESCRIPTORS)
    where = f"created_date > '{since}' AND descriptor in ({desc}) AND latitude IS NOT NULL"
    params = {
        "$select": "unique_key,created_date,closed_date,status,descriptor,borough,"
                   "incident_address,cross_street_1,cross_street_2,latitude,longitude,resolution_description",
        "$where": where,
        "$order": "unique_key",
    }
    print(f"311: pulling {DESCRIPTORS} since {since} ...")
    rows = list(paged(NYC_311, params))
    print(f"311: {len(rows)} rows")
    return rows, since


def aggregate_311(rows):
    cells = defaultdict(lambda: {"n": 0, "no_action": 0, "action": 0, "open": 0, "other": 0,
                                 "desc": Counter(), "addr": Counter(), "boro": Counter(),
                                 "lat": 0.0, "lon": 0.0, "hours": [0] * 24})
    boro = defaultdict(lambda: {"n": 0, "no_action": 0, "action": 0, "open": 0, "other": 0,
                                "resolve_hours": []})
    weekly = Counter()
    for r in rows:
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except (KeyError, ValueError):
            continue
        if not (40.4 < lat < 41.0 and -74.3 < lon < -73.6):
            continue
        k = (round(lat, GRID), round(lon, GRID))
        c = cells[k]
        cls = classify(r.get("status"), r.get("resolution_description"))
        c["n"] += 1
        c[cls] += 1
        c["desc"][r.get("descriptor", "")] += 1
        addr = r.get("incident_address") or " & ".join(
            x for x in (r.get("cross_street_1"), r.get("cross_street_2")) if x) or ""
        if addr:
            c["addr"][addr.title()] += 1
        b = (r.get("borough") or "Unspecified").title()
        c["boro"][b] += 1
        c["lat"] += lat
        c["lon"] += lon
        try:
            created = datetime.fromisoformat(r["created_date"])
            c["hours"][created.hour] += 1
            weekly[created.strftime("%G-W%V")] += 1
        except (KeyError, ValueError):
            created = None
        bb = boro[b]
        bb["n"] += 1
        bb[cls] += 1
        if created and r.get("closed_date"):
            try:
                closed = datetime.fromisoformat(r["closed_date"])
                bb["resolve_hours"].append((closed - created).total_seconds() / 3600)
            except ValueError:
                pass

    hotspots = []
    for k, c in sorted(cells.items(), key=lambda kv: -kv[1]["n"])[:TOP_CELLS]:
        closed = c["n"] - c["open"]
        hotspots.append({
            "lat": round(c["lat"] / c["n"], 5),
            "lon": round(c["lon"] / c["n"], 5),
            "n": c["n"],
            "no_action": c["no_action"],
            "action": c["action"],
            "open": c["open"],
            "rate": round(c["no_action"] / closed, 3) if closed else None,
            "desc": c["desc"].most_common(1)[0][0],
            "addr": c["addr"].most_common(1)[0][0] if c["addr"] else "",
            "boro": c["boro"].most_common(1)[0][0],
            "peak_hour": max(range(24), key=lambda h: c["hours"][h]),
        })

    boroughs = {}
    for b, s in boro.items():
        closed = s["n"] - s["open"]
        rh = sorted(s["resolve_hours"])
        boroughs[b] = {
            "n": s["n"], "no_action": s["no_action"], "action": s["action"], "open": s["open"],
            "rate": round(s["no_action"] / closed, 3) if closed else None,
            "median_resolve_hours": round(rh[len(rh) // 2], 1) if rh else None,
        }
    return hotspots, boroughs, len(cells), dict(sorted(weekly.items()))


# ---------------------------------------------------------------- MTA -------
def fetch_speeds():
    latest = get(MTA_SPEEDS, {"$select": "max(timestamp) as t"})[0]["t"]
    dt = datetime.fromisoformat(latest)
    year, month = dt.year, dt.month
    print(f"MTA: latest month in {MTA_SPEEDS.rsplit('/',1)[1].split('.')[0]} is {year}-{month:02d}; aggregating ...")
    params = {
        "$select": "route_id,direction,borough,route_type,timepoint_stop_name,next_timepoint_stop_name,"
                   "timepoint_stop_latitude as lat1,timepoint_stop_longitude as lon1,"
                   "next_timepoint_stop_latitude as lat2,next_timepoint_stop_longitude as lon2,"
                   "sum(average_travel_time*bus_trip_count) as t,"
                   "sum(road_distance*bus_trip_count) as d,sum(bus_trip_count) as n",
        "$where": f"year='{year}' AND month='{month}'",
        "$group": "route_id,direction,borough,route_type,timepoint_stop_name,next_timepoint_stop_name,"
                  "lat1,lon1,lat2,lon2",
    }
    segs = []
    route_t, route_d, route_n = Counter(), Counter(), Counter()
    boro_t, boro_d = Counter(), Counter()
    for r in paged(MTA_SPEEDS, params, page=20000):
        try:
            t, d, n = float(r["t"]), float(r["d"]), int(float(r["n"]))
        except (KeyError, ValueError):
            continue
        if t <= 0 or d <= 0:
            continue
        mph = d / t * 60.0  # travel time is in minutes
        b = (r.get("borough") or "").title()
        route_t[r["route_id"]] += t; route_d[r["route_id"]] += d; route_n[r["route_id"]] += n
        boro_t[b] += t; boro_d[b] += d
        if n < MIN_TRIPS or d / n < 0.15 or mph > 60:
            continue  # too few trips, very short hops, or GPS junk
        segs.append({
            "route": r["route_id"], "dir": r.get("direction", ""), "boro": b,
            "type": r.get("route_type", ""),
            "from": r["timepoint_stop_name"].title(), "to": r["next_timepoint_stop_name"].title(),
            "lat1": round(float(r["lat1"]), 5), "lon1": round(float(r["lon1"]), 5),
            "lat2": round(float(r["lat2"]), 5), "lon2": round(float(r["lon2"]), 5),
            "mph": round(mph, 2), "miles": round(d / n, 2), "trips": n,
        })
    print(f"MTA: {len(segs)} ranked segments, {len(route_t)} routes")
    segs.sort(key=lambda s: s["mph"])
    routes = sorted(
        ({"route": k, "mph": round(route_d[k] / route_t[k] * 60, 2), "trips": route_n[k]}
         for k in route_t if route_t[k] > 0 and route_n[k] >= 1000),
        key=lambda x: x["mph"])
    boro_speed = {b: round(boro_d[b] / boro_t[b] * 60, 2) for b in boro_t if boro_t[b] > 0 and b}
    return {
        "month": f"{year}-{month:02d}",
        "slowest_segments": segs[:TOP_SEGMENTS],
        "slowest_routes": routes[:20],
        "fastest_routes": routes[-10:][::-1],
        "borough_mph": boro_speed,
        "segments_ranked": len(segs),
    }


# ------------------------------------------------------------ boroughs -------
def _dp(pts, eps):
    """Douglas-Peucker, iterative."""
    if len(pts) < 3:
        return pts
    if pts[0] == pts[-1]:  # closed ring: split at the farthest point so the chord isn't degenerate
        x0, y0 = pts[0]
        m = max(range(1, len(pts) - 1), key=lambda i: (pts[i][0] - x0) ** 2 + (pts[i][1] - y0) ** 2)
        return _dp(pts[:m + 1], eps) + _dp(pts[m:], eps)[1:]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]; bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy) or 1e-12
        best, bi = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            dist = abs(dy * px - dx * py + bx * ay - by * ax) / L
            if dist > best:
                best, bi = dist, i
        if best > eps and bi > 0:
            keep[bi] = True
            stack.append((a, bi)); stack.append((bi, b))
    return [p for p, k in zip(pts, keep) if k]


def fetch_boroughs(eps=0.0012, min_pts=12):
    print("boroughs: pulling + simplifying ...")
    rows = get(BORO, {"$select": "boroname,the_geom"})
    out = []
    for r in rows:
        polys = []
        for poly in r["the_geom"]["coordinates"]:
            ring = _dp([(round(x, 4), round(y, 4)) for x, y in poly[0]], eps)
            if len(ring) >= min_pts:
                polys.append([[x, y] for x, y in ring])
        out.append({"name": r["boroname"], "polys": polys})
    return out


# ------------------------------------------------------------------ main ------
def main():
    rows, since = fetch_311()
    hotspots, boroughs, ncells, weekly = aggregate_311(rows)
    speeds = fetch_speeds()
    boro_geo = fetch_boroughs()
    total_no = sum(b["no_action"] for b in boroughs.values())
    total_closed = sum(b["n"] - b["open"] for b in boroughs.values())
    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "window_days": DAYS,
        "since": since[:10],
        "descriptors": DESCRIPTORS,
        "grid_decimals": GRID,
        "totals": {"complaints": len(rows), "cells": ncells,
                   "no_action_rate": round(total_no / total_closed, 3) if total_closed else None},
        "boroughs": boroughs,
        "weekly": weekly,
        "hotspots": hotspots,
        "bus": speeds,
        "borough_outline": boro_geo,
        "sources": {
            "311": "https://data.cityofnewyork.us/d/erm2-nwe9",
            "bus_speeds": "https://data.ny.gov/d/kufs-yh3x",
            "boroughs": "https://data.cityofnewyork.us/d/gthc-hcne",
        },
    }
    with open(OUT, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    kb = os.path.getsize(OUT) / 1024
    print(f"wrote {OUT} ({kb:.0f} KB); outline ~{len(json.dumps(boro_geo))/1024:.0f} KB")
    print(f"complaints={len(rows)} cells={ncells} no_action_rate={data['totals']['no_action_rate']} "
          f"bus_month={speeds['month']} slowest={speeds['slowest_segments'][0] if speeds['slowest_segments'] else None}")


if __name__ == "__main__":
    main()
