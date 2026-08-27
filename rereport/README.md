# Re-Report

Look up a NYC 311 service request (or an address), see what the agency actually did,
and re-file with the history attached.

One static page, no build step, no server: `site/index.html`. Open it in a browser.

- Enter a 311 SR number (the `unique_key`, e.g. `70193712`) or a street address
  (`1201 2 Avenue`).
- Queries NYC Open Data (`erm2-nwe9`) directly from the browser.
- Shows status, agency, resolution text, and the address's full complaint timeline
  with a repeat count. Closed requests whose resolution text says things like
  "not observed", "no violation", "unable to", "referred", "could not", or
  "duplicate" are flagged **closed without visible action** (same heuristic as
  the ghost tracker).
- The Re-report button produces a paste-ready description ("This is the Nth report
  of this issue at ADDRESS. Prior SR numbers: ... Prior closures: ...") plus links
  to the matching official NYC311 filing page. Nothing is submitted for you.

Privacy: nothing is stored and nothing is sent anywhere except
`data.cityofnewyork.us`.

Caveats: Open Data lags the portal by roughly a day; address matching is exact on
311's normalized form (house number + street, digits for numbered streets);
history is capped at the latest 50 records.
