#!/usr/bin/env python3
"""311 Ghost Tracker — build step.

Pulls the last N days of NYC 311 service requests from NYC Open Data (Socrata,
dataset erm2-nwe9), scores every agency and community board on how often
complaints are closed *without* anything being done and how often the same
problem gets reported again at the same address, then writes site/data.json.

Dependencies: Python 3.8+ and `requests`. No app token required.

Usage:  python3 build.py [--days 90] [--out site/data.json] [--page 50000]
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import requests

API = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
FIELDS = [
    "unique_key", "created_date", "closed_date", "agency", "agency_name",
    "complaint_type", "incident_address", "community_board", "borough",
    "status", "resolution_description",
]

# ---------------------------------------------------------------------------
# "Closed without action" heuristic.
#
# A closed request counts as closed-without-action when its resolution text
# matches one of these phrases AND does not also say a concrete fix/enforcement
# happened (ACTION_PATTERNS). The phrases were picked by reading the most
# common resolution descriptions in the dataset; the full list is documented
# in the README and shown on the site's methodology section.
# ---------------------------------------------------------------------------
GHOST_PATTERNS = [
    r"\bnot observed\b",
    r"\bno (criminal )?violation\b",
    r"\bno evidence\b",
    r"\bno condition\b",
    r"\bfound no\b",
    r"\bdid not violate\b",
    r"\bno violations were issued\b",
    r"\bunable to\b",
    r"\bcould ?n['o]t\b",
    r"\bcan ?not\b",
    r"\bcouldn't\b",
    r"\bnot able to\b",
    r"\bnot necessary\b",
    r"\bno work is necessary\b",
    r"\bno further action\b",
    r"\breferred\b",
    r"\bduplicate\b",
    r"\bearlier complaint\b",
    r"\balready (been )?reported\b",
    r"\binsufficient\b",
    r"\bnot enough information\b",
    r"\bdoes not fall under\b",
    r"\bdoes not have jurisdiction\b",
    r"\bnot (the )?responsib",
    r"\bno access\b",
    r"\bgain (access|entry)\b",
    r"\bnot found\b",
    r"\bno longer (present|at|exists)\b",
    r"\bcondition (has been )?resolved prior\b",
    r"\bclosed it\b",           # "reviewed this complaint and closed it"
    r"\bcould be closed\b",
    r"\bnot accept\b",
    r"\bno response\b",
]
ACTION_PATTERNS = [
    r"\bissued (a )?(summons|notice|violation)",
    r"\bviolations? (were|was) issued\b",
    r"\bsummons\b",
    r"\brepaired\b",
    r"\bcleaned\b",
    r"\bremoved\b",
    r"\bcollected\b",
    r"\bcorrected\b",
    r"\bshut\b",
    r"\bcompleted the requested work\b",
    r"\bcreated a work order\b",
    r"\bwork order\b",
    r"\brestored\b",
    r"\bmailed you\b",
    r"\bsent official written notification\b",
    r"\bfound violations\b",
]
GHOST_RE = re.compile("|".join(GHOST_PATTERNS), re.I)
ACTION_RE = re.compile("|".join(ACTION_PATTERNS), re.I)

REREPORT_WINDOW = timedelta(days=30)


def is_ghost(text):
    if not text:
        return False
    return bool(GHOST_RE.search(text)) and not ACTION_RE.search(text)


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def fetch(days, page_size, log=print):
    """Pull the window one calendar day at a time.

    Socrata handles a bounded created_date range without ORDER BY very fast
    (well under a second per day), while a single filtered query with
    $order/$offset over ~1M rows times out. Each day is paged with
    $limit/$offset in case it exceeds page_size (a normal day is ~11k rows).
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    session = requests.Session()
    session.headers["User-Agent"] = "zohran-ghost-tracker/1.0 (+https://github.com/zyads/zohran)"
    token = os.environ.get("SOCRATA_APP_TOKEN")
    if token:
        session.headers["X-App-Token"] = token

    def get(params):
        for attempt in range(8):
            try:
                r = session.get(API, params=params, timeout=120)
                if r.status_code == 429 or r.status_code >= 500:
                    wait = min(60, 2 ** attempt * 3)
                    log(f"  HTTP {r.status_code}, retrying in {wait}s")
                    time.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            except (requests.RequestException, ValueError) as e:
                wait = min(60, 2 ** attempt * 3)
                log(f"  {e!r}, retrying in {wait}s")
                time.sleep(wait)
        raise SystemExit("gave up fetching from Socrata")

    rows = []
    day = start
    while day < now:
        nxt = day + timedelta(days=1)
        where = (f"created_date >= '{day:%Y-%m-%dT%H:%M:%S}' "
                 f"AND created_date < '{nxt:%Y-%m-%dT%H:%M:%S}'")
        offset = 0
        while True:
            page = get({"$select": ",".join(FIELDS), "$where": where,
                        "$limit": page_size, "$offset": offset})
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        log(f"  {day:%Y-%m-%d}: {len(rows):,} rows so far")
        day = nxt
    return rows, start.strftime("%Y-%m-%dT%H:%M:%S")


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def median_hours(vals):
    return round(statistics.median(vals), 1) if vals else None


def build(rows, since, days):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Normalise into compact records.
    recs = []
    for r in rows:
        created = parse_ts(r.get("created_date"))
        if not created:
            continue
        closed = parse_ts(r.get("closed_date"))
        status = (r.get("status") or "").strip()
        is_closed = status.lower() == "closed" and closed is not None
        # Some records carry a closed_date that predates creation (data entry
        # quirks); treat those as closed with unknown duration.
        hours = None
        if is_closed and closed >= created:
            hours = (closed - created).total_seconds() / 3600.0
        recs.append({
            "agency": (r.get("agency") or "UNKNOWN").strip(),
            "agency_name": (r.get("agency_name") or "").strip(),
            "ctype": (r.get("complaint_type") or "Unknown").strip(),
            "addr": (r.get("incident_address") or "").strip().upper(),
            "cb": (r.get("community_board") or "Unspecified").strip(),
            "boro": (r.get("borough") or "").strip(),
            "created": created,
            "closed": closed if is_closed else None,
            "hours": hours,
            "ghost": is_closed and is_ghost(r.get("resolution_description")),
        })

    # Re-report detection: same address + complaint type, new request created
    # within 30 days after an earlier request was closed.
    groups = defaultdict(list)
    for rec in recs:
        if rec["addr"] and not rec["addr"].startswith("UNKNOWN"):
            groups[(rec["addr"], rec["ctype"])].append(rec)
    for key, lst in groups.items():
        lst.sort(key=lambda x: x["created"])
        created_times = [x["created"] for x in lst]
        for i, rec in enumerate(lst):
            rec["rereported"] = False
            if not rec["closed"]:
                continue
            limit = rec["closed"] + REREPORT_WINDOW
            # any later-created request in (closed, closed+30d]
            for other in lst[i + 1:]:
                if other["created"] <= rec["closed"]:
                    continue
                if other["created"] <= limit:
                    rec["rereported"] = True
                break
    for rec in recs:
        rec.setdefault("rereported", False)

    def summarise(lst):
        total = len(lst)
        closed = [x for x in lst if x["closed"]]
        ghost = [x for x in closed if x["ghost"]]
        # Only closes that had a full 30-day window inside our data can be
        # judged for re-reports; otherwise the rate is biased downward.
        eligible = [x for x in closed if x["closed"] + REREPORT_WINDOW <= now and x["addr"]]
        rer = [x for x in eligible if x["rereported"]]
        hrs = [x["hours"] for x in closed if x["hours"] is not None]
        return {
            "total": total,
            "closed": len(closed),
            "closed_pct": pct(len(closed), total),
            "ghost": len(ghost),
            "ghost_pct": pct(len(ghost), len(closed)),
            "rereport_eligible": len(eligible),
            "rereported": len(rer),
            "rereport_pct": pct(len(rer), len(eligible)),
            "median_hours_to_close": median_hours(hrs),
        }

    by_agency = defaultdict(list)
    by_cb = defaultdict(list)
    by_agency_ctype = defaultdict(list)
    names = {}
    for rec in recs:
        by_agency[rec["agency"]].append(rec)
        by_cb[rec["cb"]].append(rec)
        by_agency_ctype[(rec["agency"], rec["ctype"])].append(rec)
        if rec["agency_name"]:
            names.setdefault(rec["agency"], rec["agency_name"])

    agencies = []
    for a, lst in by_agency.items():
        s = summarise(lst)
        if s["total"] < 100:
            continue
        s.update({"agency": a, "name": names.get(a, a)})
        agencies.append(s)
    agencies.sort(key=lambda s: -s["total"])

    boards = []
    for cb, lst in by_cb.items():
        s = summarise(lst)
        if s["total"] < 100:
            continue
        s.update({"community_board": cb, "borough": lst[0]["boro"]})
        boards.append(s)
    boards.sort(key=lambda s: -s["total"])

    complaint_types = []
    for (a, ct), lst in by_agency_ctype.items():
        s = summarise(lst)
        if s["total"] < 200:
            continue
        s.update({"agency": a, "complaint_type": ct})
        complaint_types.append(s)
    complaint_types.sort(key=lambda s: -s["total"])

    # Top addresses by number of re-reported closes.
    addr_stats = defaultdict(lambda: {"total": 0, "closed": 0, "ghost": 0, "rereported": 0, "types": defaultdict(int)})
    for rec in recs:
        if not rec["addr"]:
            continue
        key = (rec["addr"], rec["boro"] or rec["cb"])
        st = addr_stats[key]
        st["total"] += 1
        st["types"][rec["ctype"]] += 1
        if rec["closed"]:
            st["closed"] += 1
            if rec["ghost"]:
                st["ghost"] += 1
            if rec["rereported"]:
                st["rereported"] += 1
    top_addresses = []
    for (addr, boro), st in addr_stats.items():
        if st["rereported"] == 0:
            continue
        types = sorted(st["types"].items(), key=lambda kv: -kv[1])[:3]
        top_addresses.append({
            "address": addr,
            "borough": boro,
            "total": st["total"],
            "closed": st["closed"],
            "ghost": st["ghost"],
            "ghost_pct": pct(st["ghost"], st["closed"]),
            "rereported": st["rereported"],
            "top_complaints": [t for t, _ in types],
        })
    top_addresses.sort(key=lambda s: (-s["rereported"], -s["total"]))
    top_addresses = top_addresses[:20]

    citywide = summarise(recs)
    return {
        "generated_at": now.replace(tzinfo=timezone.utc).isoformat(timespec="seconds"),
        "window_days": days,
        "window_start": since,
        "rereport_window_days": REREPORT_WINDOW.days,
        "citywide": citywide,
        "agencies": agencies,
        "community_boards": boards,
        "complaint_types": complaint_types,
        "top_addresses": top_addresses,
        "heuristic": {
            "ghost_patterns": GHOST_PATTERNS,
            "action_patterns": ACTION_PATTERNS,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--page", type=int, default=50000)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "site", "data.json"))
    args = ap.parse_args()

    print(f"Fetching last {args.days} days of NYC 311 requests ...")
    rows, since = fetch(args.days, args.page)
    print(f"Scoring {len(rows):,} requests ...")
    data = build(rows, since, args.days)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(data, f, separators=(",", ":"))
    c = data["citywide"]
    print(f"Wrote {args.out}")
    print(f"  total {c['total']:,}  closed {c['closed']:,} ({c['closed_pct']}%)  "
          f"closed-without-action {c['ghost']:,} ({c['ghost_pct']}% of closed)  "
          f"re-reported {c['rereported']:,}/{c['rereport_eligible']:,} ({c['rereport_pct']}%)  "
          f"median hours to close {c['median_hours_to_close']}")
    print(f"  agencies {len(data['agencies'])}  community boards {len(data['community_boards'])}  "
          f"top addresses {len(data['top_addresses'])}")


if __name__ == "__main__":
    main()
