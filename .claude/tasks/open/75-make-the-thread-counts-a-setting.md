---
title: Make the io server's worker count and the session probe's thread count settings
stage: I
area: mcp
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "feat: the io server's thread counts are settings"
---

## Why

On 2026-09-29 the lead asked for the number of threads io-guard uses to be a setting, since a fixed 4 can be
too many on a small machine. Two places fix it at 4 today:

- `plugins/io-guard/scripts/ioguard/mcp/server.py`: `WORKERS = 4`, the `ThreadPoolExecutor` that runs each
  `tools/call`, hook tools and io tools alike. Every session runs its own server, so 3 sessions hold 12 workers.
- `plugins/io-guard/scripts/ioguard/checks/session_probe.py`: `ThreadPoolExecutor(max_workers=4)`, which runs
  the session probe's tool version checks at the first hook call.

## What to build

- A user-only key in `lib/config.py` for the server's workers, such as `io.server.workers`, default 4, at least
  1. A project file may not set it (D24), since one server serves every project a session touches.
- A key for the probe's threads, or the probe takes the same key. Decide which, and record it in context.md.
- `mcp/server.py` reads the key from the user's config once, when it starts, and the page and `io.config` say a
  change applies from the next session.
- Measure first: time a session's hook calls with 1, 2 and 4 workers through `tools/replay.py` with test checks,
  or a `live-*` probe, so the default and the minimum rest on numbers.

## Where

`plugins/io-guard/scripts/ioguard/mcp/server.py`, `plugins/io-guard/scripts/ioguard/checks/session_probe.py`,
`plugins/io-guard/scripts/ioguard/lib/config.py`, `docs/design/architecture.md` (section 8, the thread table),
`README.md`.

## Done when

- A server started with the key at 1 runs every call through one worker, and a test proves it.
- The thread table in `architecture.md` names the key.
