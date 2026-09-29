---
title: Make the thread counts a setting, and shrink old telemetry's command heads after a setting's days
stage: I
area: mcp
created: 2026-09-29
status: done
depends-on: [89]
findings: [security-review-2026-09-29-8]
platforms: [windows, macos]
commit: "feat: thread counts and command-head retention are settings"
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
- **Folded in from task 93, the lead's answer A on 2026-09-29.** Every telemetry line keeps `cmd_head`, the
  first 200 characters of the command, for `telemetry.retention_days` (90). After a user-only setting's days,
  the io server's retention pass at its start (task 89, `mcp/server.py` `expire`) rewrites each older line's
  `cmd_head` to its program name only. The lead: "obviously stays in config too (so user can change it)". So
  it is a key, such as `telemetry.cmd_head_days`, with a default to settle (7, as `io.saved_days`, fits), 0
  keeping the heads whole. `tools/report.py` and the stats page must read a shrunk head.

## Where

`plugins/io-guard/scripts/ioguard/mcp/server.py`, `plugins/io-guard/scripts/ioguard/checks/session_probe.py`,
`plugins/io-guard/scripts/ioguard/lib/config.py`, `docs/design/architecture.md` (section 8, the thread table),
`README.md`.

## Done when

- A server started with the key at 1 runs every call through one worker, and a test proves it.
- The thread table in `architecture.md` names the key.
- A telemetry line past the command-head key's days holds only its program in `cmd_head` after the server
  starts, a newer one keeps its 200 characters, and the README names the key.

## What changed

- `lib/config.py`: `io.server.workers` (4, at least 1 through `at_least_one`, user-only) and
  `telemetry.cmd_head_days` (7, 0 keeps heads whole, user-only).
- `mcp/server.py`: `Server` takes its worker count, and `main` reads the key once at the start. `expire`
  also calls `telemetry.shrink_heads`.
- `checks/session_probe.py`: the probe's pool takes `min(4, io.server.workers)`. One key for both, recorded as
  D44.
- `lib/telemetry.py`: `program_of`, the first word or the first quoted text without its folder, and
  `shrink_heads`, which rewrites each old session file's `cmd_head` values to that through `write_atomic` and
  puts the file's time back, since `expire` and the next pass read it. A file already cut is not written
  again.
- The key's help and the README say that at 1 a long `io.run` holds back every hook. The settings page shows
  the help. A change applies from the next session, which the help says.
- Docs: `docs/design/architecture.md` (the thread table, the retention row, the user-only keys),
  `README.md`, the drawing's threads hover text, which also no longer names a telemetry queue that does not
  exist, and D44 in `context.md`. D42's pointer to task 93 now points here.

Evidence:

- Measured first, with the key in place: `live-edit-parallel`, 30 `io.edit` calls from three subagents,
  took a median of 6.4 ms at 1 worker, 6.5 at 2 and 6.3 at 4 (p90 8.0, 7.0, 6.7), and all three runs ended
  with the right file. The count matters only while a long call holds a worker.
- `python tests/run_all.py`: 958 tests, OK, up from 953. New: with 1 worker a second call waits for the first
  to end, 0 workers is refused, an old file's heads keep only their program and the file keeps its time, a
  new file keeps its words, a second pass writes nothing, 0 keeps every head, and `program_of` on five
  shapes.
- Live, Claude Code 2.1.283 on Windows: a 10-day-old telemetry file holding `git commit -m 'secret words'`
  held `git` after `live-empty` started the server, still 10 days old, and a 1-day-old one kept its words.

Checked on Windows 10 on 2026-09-29. Not checked: macOS (task 36).
