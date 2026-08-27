#!/usr/bin/env python3
"""Heat & Hot Water Scoreboard — build heat/site/data.json from NYC Open Data.

Sources (all Socrata, no key needed; set SODA_APP_TOKEN for higher rate limits):
  wvxf-dwi5  HPD violations          -> heat / hot-water violations per building
  erm2-nwe9  311 service requests    -> HEAT/HOT WATER complaints per building
  tesw-yqqr  HPD registrations       -> building -> registration id, community board
  feu5-w2e2  HPD registration contacts -> registration id -> head officer / owner

Counts are aggregated server-side ($group) so the whole build is a handful of
bounded, paged queries. Two heating seasons are compared: "this" = the most
recently completed / current one, "prior" = the one before.
"""
import json, os, re, sys, time, datetime as dt
from collections import defaultdict
import requests

BASE = "https://data.cityofnewyork.us/resource/"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "site", "data.json")
PAGE = 50000
S = requests.Session()
S.headers["User-Agent"] = "zohran-heat-scoreboard/1.0 (open data civic tool)"
if os.environ.get("SODA_APP_TOKEN"):
    S.headers["X-App-Token"] = os.environ["SODA_APP_TOKEN"]


def seasons(today=None):
    """Heat season = Oct 1 .. May 31. Return (this, prior) as (label, start, end)."""
    today = today or dt.date.today()
    y = today.year if today.month >= 10 else today.year - 1
    this = (f"{y}-{str(y+1)[2:]}", dt.date(y, 10, 1), dt.date(y + 1, 6, 1))
    prior = (f"{y-1}-{str(y)[2:]}", dt.date(y - 1, 10, 1), dt.date(y, 6, 1))
    return this, prior


def fetch(ds, params, label):
    rows, offset = [], 0
    while True:
        p = dict(params, **{"$limit": PAGE, "$offset": offset})
        for attempt in range(5):
            try:
                r = S.get(BASE + ds + ".json", params=p, timeout=180)
                if r.status_code == 429:
                    time.sleep(10 * (attempt + 1)); continue
                r.raise_for_status()
                batch = r.json(); break
            except (requests.RequestException, ValueError) as e:
                print(f"  retry {attempt+1} {label}: {e}", file=sys.stderr)
                time.sleep(5 * (attempt + 1))
        else:
            raise SystemExit(f"gave up on {label}")
        rows.extend(batch)
        print(f"  {label}: {len(rows)} rows", file=sys.stderr)
        if len(batch) < PAGE:
            return rows
        offset += PAGE
        time.sleep(0.5)


def bbl(boro, block, lot):
    try:
        return f"{int(boro)}{int(block):05d}{int(lot):04d}"
    except (TypeError, ValueError):
        return None


BORO = {"1": "Manhattan", "2": "Bronx", "3": "Brooklyn", "4": "Queens", "5": "Staten Island"}
BORO_NAME = {"MANHATTAN": "1", "BRONX": "2", "BROOKLYN": "3", "QUEENS": "4", "STATEN ISLAND": "5"}


def cd_code(boro_id, board):
    """Community district as e.g. 'BK 05' -> stored as '305'."""
    try:
        b = int(board)
    except (TypeError, ValueError):
        return None
    if boro_id is None or not (1 <= b <= 18):
        return None
    return f"{boro_id}{b:02d}"


def norm_name(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", (s or "").upper())
    return re.sub(r"\s+", " ", s).strip()


def main():
    this, prior = seasons()
    print(f"seasons: this={this[0]} prior={prior[0]}", file=sys.stderr)
    HEAT = "(upper(novdescription) like '%HEAT%' OR upper(novdescription) like '%HOT WATER%')"

    # ---- 1. HPD registrations: building -> registration, CD -------------------
    regs = fetch("tesw-yqqr", {
        "$select": "buildingid,registrationid,boroid,block,lot,housenumber,streetname,zip,communityboard",
    }, "registrations")
    reg_by_bid, reg_by_bbl, bld_meta = {}, {}, {}
    for r in regs:
        b = bbl(r.get("boroid"), r.get("block"), r.get("lot"))
        if not b:
            continue
        rid = r.get("registrationid")
        reg_by_bid[r.get("buildingid")] = rid
        reg_by_bbl.setdefault(b, rid)
        bld_meta.setdefault(b, {
            "addr": f"{(r.get('housenumber') or '').strip()} {(r.get('streetname') or '').strip()}".strip(),
            "zip": r.get("zip"), "boro": r.get("boroid"),
            "cd": cd_code(r.get("boroid"), r.get("communityboard")),
        })
    del regs

    # ---- 2. Registration contacts: registration -> landlord name -------------
    contacts = fetch("feu5-w2e2", {
        "$select": "registrationid,type,firstname,lastname,corporationname",
        "$where": "type in ('HeadOfficer','CorporateOwner','IndividualOwner','JointOwner')",
    }, "contacts")
    PRI = {"HeadOfficer": 0, "IndividualOwner": 1, "JointOwner": 2, "CorporateOwner": 3}
    best = {}  # rid -> (pri, name, corp)
    corp_of = {}
    for c in contacts:
        rid = c.get("registrationid"); t = c.get("type")
        if t == "CorporateOwner":
            corp_of.setdefault(rid, norm_name(c.get("corporationname")))
        name = norm_name(f"{c.get('firstname') or ''} {c.get('lastname') or ''}") if t != "CorporateOwner" \
            else norm_name(c.get("corporationname"))
        if not name:
            continue
        if rid not in best or PRI[t] < best[rid][0]:
            best[rid] = (PRI[t], name)
    del contacts

    # ---- 3. HPD heat violations, grouped per building per season -------------
    viol = {}  # bbl -> [this, prior, open_now]
    for idx, (label, start, end) in enumerate((this, prior)):
        rows = fetch("wvxf-dwi5", {
            "$select": "buildingid,boroid,block,lot,housenumber,streetname,zip,registrationid,count(*) as n",
            "$where": f"{HEAT} AND novissueddate >= '{start}' AND novissueddate < '{end}'",
            "$group": "buildingid,boroid,block,lot,housenumber,streetname,zip,registrationid",
        }, f"violations {label}")
        for r in rows:
            b = bbl(r.get("boroid"), r.get("block"), r.get("lot"))
            if not b:
                continue
            v = viol.setdefault(b, [0, 0, 0])
            v[idx] += int(r["n"])
            if b not in bld_meta:
                bld_meta[b] = {"addr": f"{(r.get('housenumber') or '').strip()} {(r.get('streetname') or '').strip()}",
                               "zip": r.get("zip"), "boro": r.get("boroid"), "cd": None}
            if r.get("registrationid") and b not in reg_by_bbl:
                reg_by_bbl[b] = r["registrationid"]
    # currently open heat violations (any date)
    rows = fetch("wvxf-dwi5", {
        "$select": "boroid,block,lot,count(*) as n",
        "$where": f"{HEAT} AND violationstatus = 'Open' AND novissueddate >= '{prior[1]}'",
        "$group": "boroid,block,lot",
    }, "open violations")
    for r in rows:
        b = bbl(r.get("boroid"), r.get("block"), r.get("lot"))
        if b in viol:
            viol[b][2] = int(r["n"])

    # ---- 4. 311 heat complaints, grouped per BBL per season ------------------
    comp = {}  # bbl -> [this, prior]
    for idx, (label, start, end) in enumerate((this, prior)):
        rows = fetch("erm2-nwe9", {
            "$select": "bbl,incident_address,borough,community_board,count(*) as n",
            "$where": f"complaint_type like 'HEAT%' AND created_date >= '{start}' AND created_date < '{end}' AND bbl IS NOT NULL",
            "$group": "bbl,incident_address,borough,community_board",
        }, f"311 {label}")
        for r in rows:
            b = r.get("bbl")
            if not b or len(b) != 10 or b.endswith("00000000"):
                continue
            c = comp.setdefault(b, [0, 0]); c[idx] += int(r["n"])
            m = bld_meta.get(b)
            if m is None:
                bld_meta[b] = m = {"addr": r.get("incident_address") or "", "zip": None,
                                   "boro": BORO_NAME.get((r.get("borough") or "").upper()), "cd": None}
            if not m.get("cd"):
                cb = (r.get("community_board") or "").split(" ")[0]
                m["cd"] = cd_code(m.get("boro"), cb)

    # ---- 5. Assemble buildings ------------------------------------------------
    buildings = []
    for b in set(viol) | set(comp):
        m = bld_meta[b]
        v = viol.get(b, [0, 0, 0]); c = comp.get(b, [0, 0])
        rid = reg_by_bbl.get(b)
        owner = best.get(rid, (9, None))[1] if rid else None
        corp = corp_of.get(rid) if rid else None
        if v[0] + v[1] == 0 and c[0] + c[1] < 2:
            continue  # trim: one-off complaints add ~no signal and much size
        buildings.append([b, m["addr"].title(), m.get("zip") or "", m.get("cd") or "",
                          v[0], v[1], v[2], c[0], c[1], owner or "", corp or ""])
    # rank: violations this season, then 311 complaints, then prior-season violations
    buildings.sort(key=lambda x: (-x[4], -x[7], -x[5]))

    # ---- 6. Landlords ----------------------------------------------------------
    ll = defaultdict(lambda: {"b": 0, "v": 0, "vp": 0, "c": 0, "cp": 0, "o": 0, "cds": defaultdict(int), "corps": set(), "ex": []})
    for x in buildings:
        key = x[9] or x[10]
        if not key:
            continue
        L = ll[key]
        L["b"] += 1; L["v"] += x[4]; L["vp"] += x[5]; L["o"] += x[6]; L["c"] += x[7]; L["cp"] += x[8]
        if x[3]: L["cds"][x[3]] += x[4] * 10 + x[7]
        if x[10]: L["corps"].add(x[10])
        if len(L["ex"]) < 3: L["ex"].append([x[0], x[1]])
    landlords = []
    for name, L in ll.items():
        if L["v"] + L["vp"] == 0:
            continue
        landlords.append({
            "n": name, "b": L["b"], "v": L["v"], "vp": L["vp"], "o": L["o"], "c": L["c"], "cp": L["cp"],
            "vpb": round(L["v"] / L["b"], 2),
            "cds": sorted(L["cds"], key=L["cds"].get, reverse=True)[:5],
            "corps": sorted(L["corps"])[:6], "ex": L["ex"],
        })
    landlords.sort(key=lambda L: (-L["v"], -L["c"]))
    landlords = landlords[:1500]

    cds = sorted({x[3] for x in buildings if x[3]})
    out = {
        "built": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        "season": this[0], "prior": prior[0],
        "fields": ["bbl", "addr", "zip", "cd", "viol", "viol_prior", "viol_open", "c311", "c311_prior", "owner", "corp"],
        "totals": {"buildings": len(buildings),
                   "viol": sum(v[0] for v in viol.values()), "viol_prior": sum(v[1] for v in viol.values()),
                   "c311": sum(c[0] for c in comp.values()), "c311_prior": sum(c[1] for c in comp.values())},
        "cds": cds, "buildings": buildings, "landlords": landlords,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT} {os.path.getsize(OUT)/1e6:.1f} MB — {len(buildings)} buildings, {len(landlords)} landlords", file=sys.stderr)
    print(json.dumps(out["totals"]), file=sys.stderr)


if __name__ == "__main__":
    main()
