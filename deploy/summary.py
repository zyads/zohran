#!/usr/bin/env python3
"""Write dist/summary.json: one headline number per tool, pulled from each tool's
own data.json, so the landing page never has to download the big files."""
import json, sys, os, datetime

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "dist", "summary.json")

def load(tool):
    for p in (os.path.join(root, "dist", tool, "data.json"),
              os.path.join(root, tool, "site", "data.json")):
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    return None

s = {"generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}

g = load("ghost-tracker")
if g:
    c = g.get("citywide", {})
    s["ghost"] = {"ghost_pct": c.get("ghost_pct"), "total": c.get("total"),
                  "closed": c.get("closed"), "window_days": g.get("window_days")}
    s["rereport"] = {"rereport_pct": c.get("rereport_pct"),
                     "rereported": c.get("rereported"),
                     "window_days": g.get("rereport_window_days")}

h = load("heat")
if h:
    t = h.get("totals", {})
    viol, prior = t.get("viol"), t.get("viol_prior")
    s["heat"] = {"violations": viol, "violations_prior": prior,
                 "change_pct": round((viol - prior) / prior * 100) if viol and prior else None,
                 "buildings": t.get("buildings"), "complaints": t.get("c311"),
                 "season": h.get("season")}

l = load("lanes")
if l:
    t = l.get("totals", {})
    s["lanes"] = {"no_action_pct": round(t["no_action_rate"] * 100, 1) if t.get("no_action_rate") is not None else None,
                  "complaints": t.get("complaints"), "window_days": l.get("window_days")}

os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w") as f:
    json.dump(s, f, indent=1)
print("wrote", out, {k: v for k, v in s.items() if k != "generated"})
