---
title: Stop the settings page's server when no open page has asked for a while
stage: I
area: mcp
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [33]
findings: []
platforms: [windows, macos]
commit: "feat: the settings page's server stops once no page has asked for five minutes"
---

## Why

Task 33's page server starts on the first `io.dashboard` call and runs until the io server stops, so a page
closed a minute later leaves a server up for the rest of the session. The lead asked on 2026-09-29 for it to
run only while the page is used: "idle stop, timer as config, 5 minutes default".

## What to build

- The open page asks the server every 30 seconds, so a page left open keeps it up.
- The server stops itself once nothing asked it for `io.dashboard.idle_minutes`, 5 by default. 0 keeps it up
  until the session ends.
- The next `io.dashboard` starts a new one, on a new port with a new token.
- Tests: a server with no request stops after its idle time, and one that is asked stays up.

## Where

`plugins/io-guard/scripts/ioguard/mcp/dashboard_http.py`, `plugins/io-guard/scripts/ioguard/mcp/tools_dashboard.py`,
`plugins/io-guard/scripts/ioguard/lib/config.py`, `plugins/io-guard/ui/dashboard.html`.

## Done when

- A page closed for longer than the idle time leaves no server, and the next "open settings" works.

## What changed

- `mcp/dashboard_http.py`: `Dashboard` takes `idle_s` and `on_stop`. Each allowed request resets `last`, and a
  watcher thread checks every quarter of the idle time, at most 5 seconds, and stops the server once `expired`.
  `GET /api/ping` answers an open page.
- `mcp/tools_dashboard.py`: `io.dashboard` reads `io.dashboard.idle_minutes`, `forget` drops a stopped server
  unless a newer one took its place, and the tool's note says the page stops and how to reopen it.
- `lib/config.py`: `io.dashboard.idle_minutes`, 5 by default, 0 for never, the user's alone.
- `ui/dashboard.html`: a ping every 30 seconds, and a banner naming the fix when one fails.
- Tests: `tests/mcp/test_tools_dashboard.py` (3: the idle arithmetic with no waiting, a real server with a
  0.05-second idle stopping and calling `on_stop`, and the tool's note and a new URL after a stop). The page
  test now lists `/api/ping` among its calls.
- Docs: `docs/design/architecture.md` (the dashboard page), `README.md` (Configure it), the skill tables.

Evidence:

- `python tests/run_all.py` from Git Bash ran 892 tests, all passing, up from 889. The dashboard tests passed
  three runs in a row.
- `live-dashboard` passed on 2.1.283 on Windows on 2026-09-29.
- Not seen live: a page closed for five minutes in the lead's session. The unit test runs the same watcher
  with a shorter time.
