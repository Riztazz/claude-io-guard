---
title: Keep the settings page's token out of history, and bound each request the page server takes
stage: H
area: mcp
created: 2026-09-29
status: done
depends-on: []
findings: [security-review-2026-09-29-5, security-review-2026-09-29-9]
platforms: [windows, macos]
commit: "fix: the settings page's token leaves the address bar and each request is bounded"
---

## Why

Fable's security review of 2026-09-29, findings 5 and 9, checked in the code the same day.

- `ui/dashboard.html` reads the token from `location.search` and leaves it in the address bar and the browser's
  history, and `mcp/dashboard_http.py` accepts it from the query string on every request. Anything that learns it
  can write settings and delete all telemetry.
- `mcp/dashboard_http.py` runs a `ThreadingHTTPServer` whose handler has no timeout, and reads
  `int(Content-Length)` unguarded, so a negative length reads to the end of the stream. A local page that finds
  the port can hold connections open and pile threads inside the io server.

## What to build

- The page calls `history.replaceState` to drop the token from the URL after reading it, and the API takes the
  token from the header only. `GET /` keeps the query token, since that is how the page opens.
- `Handler.timeout = 10`, and a `Content-Length` that is missing, negative or over `BODY_LIMIT` answers 400 or 415.
- Tests for each.

## Done when

- After the page loads, the address bar holds no token, an API call with the token in the query answers 403, a
  negative length answers 400, and a connection that sends nothing closes within the timeout.

## What changed

- `mcp/dashboard_http.py`: an API request takes the token from `X-IOGuard-Token` alone. `GET /` serves the
  page with no token, since the page holds no setting and a reload has no token in its URL. The `Host` test
  holds for every request. `Handler.timeout` is `REQUEST_TIMEOUT_S`, 10 seconds. `body_length` accepts a
  `Content-Length` from 0 to `BODY_LIMIT`, and anything else, missing included, answers 400 and closes the
  connection. A wrong `Content-Type` still answers 415.
- `ui/dashboard.html`: the page reads `?token=` once, keeps it in the tab's `sessionStorage`, and calls
  `history.replaceState(null, "", location.pathname)`. Where storage is blocked it keeps the token in the URL,
  so the page still works.
- Docs: `docs/design/architecture.md` (who may ask, and the bounds) and `README.md`. The drawing's "behind a
  token" still holds.

Evidence:

- `python tests/run_all.py`: 939 tests, OK, up from 936. New: the API with the token in the query answers
  403, the page with no token 200 and from another host 403. A body with no length, a negative one, one that
  is not a number and one over the limit each answer 400. A connection that sends nothing is closed after the
  timeout (patched to 0.3 s). The page calls `history.replaceState`.
- Live in the desktop app's browser pane on 2026-09-29, from this checkout: the page opened from
  `http://127.0.0.1:61557/?token=...` showed its 88 settings, the address bar then read
  `http://127.0.0.1:61557/`, and a reload loaded the settings again from `sessionStorage`.

Checked on Windows 10 on 2026-09-29. Not checked: macOS (task 36).
