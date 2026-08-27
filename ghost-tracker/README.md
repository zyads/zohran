# 311 Ghost Tracker

Where NYC 311 quietly gives up.

Scores every city agency and community board on how often 311 complaints are
**closed without action** ("condition not observed", "no violation", "unable to
gain access", "referred", "duplicate", …) and how often the **same problem is
reported again** at the same address within 30 days of a close. Also lists the
20 addresses that keep coming back, and median time-to-close.

Public data only (NYC Open Data, dataset `erm2-nwe9`). No servers, no accounts,
no tracking. Output is one `data.json` and one static HTML page.

## Run

    make            # or: python3 build.py
    make serve      # http://localhost:8311

Requires Python 3.8+ and `requests`. Pulls the last 90 days (~1M rows, a few
minutes) and writes `site/data.json`. `--days N` changes the window. Set
`SOCRATA_APP_TOKEN` if you hit rate limits (not required).

## How "closed without action" is decided

The city publishes no such category. A closed request counts if its resolution
description matches a phrase like *not observed / no violation / no evidence /
unable to / could not / not necessary / referred / duplicate / insufficient /
does not fall under / gain access / not found*, and does not also say something
was done (*summons / repaired / cleaned / removed / corrected / work order /
violations issued / …*). The exact regex lists live at the top of `build.py` and
are printed in the page's methodology section.

Re-report: same `incident_address` + `complaint_type`, new request created
within 30 days after an earlier request's `closed_date`. Only closes with a
full 30 days of data after them are counted in the rate, so the newest month
of closes is excluded.

Caveats: text heuristic; 90-day window is seasonal; intake-level closes
(duplicate/referral) count the same as post-inspection closes; address matching
is exact-string; repeat callers (some addresses file the same complaint hundreds
of times) inflate the re-report rate, especially for NYPD noise. Read the numbers as "where reporting is least likely to lead
anywhere", not as proof of neglect.
