---
title: Find why an mcp_tool hook now takes 38 ms where it took 1.2 ms
stage: I
area: launch
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [06, 23]
findings: []
platforms: [windows]
commit: "docs: what an mcp_tool hook costs, and why it changed"
---

## Why

Every guarded tool call reaches io-guard through an `mcp_tool` hook, and the README and the design rest on that
path costing about a millisecond. On 2026-09-27 `launch-mcp`, 100 Bash calls against the probes' own server,
measured 1.2 ms at p50 on the `claude` CLI 2.1.283. On 2026-09-28 it measured 37.9 ms at p50, 43.2 at p95 and
1.1 at its fastest, twice, once beside `launch-exec` and once alone, on the same release. io-guard's own hooks
in `live-empty` and `live-answers` the same day ranged from 1.8 to 46.9 ms over 9 calls. The probe server
changed in that time only in answers `launch-mcp` never asks for.

## What to build

- Find the cause. The candidates:
  - this machine's load, since the desktop app ran several sessions during the second measurement
  - a change inside Claude Code that its version string doesn't show
  - a Python or Windows update
- Compare `launch-mcp` with the desktop app closed, on the desktop's 2.1.281, and after a reboot.
- Record what an `mcp_tool` hook costs, with the conditions, in `docs/launcher.md` and `docs/live-checks.md`.

## Where

`tools/probes/run_probe.py`, `docs/launcher.md`, `docs/live-checks.md`, `.claude/tasks/context.md`.

## Done when

- The 1.2 ms or the 37.9 ms is explained, and the docs state the number that holds with its conditions.

## What changed

The cause is none of the three candidates. The lead's installed io-guard ran inside the two slow sessions,
before `without_installed()` in `run_probe.py` turned it off in every probe the same day.

- Each run of 13:32 and 13:35 UTC timed 200 PreToolUse hooks for 100 Bash calls. Its `debug.txt` names
  `plugin:io-guard:io` 207 and 208 times, against 0 in the fast runs.
- Split by slot, each call's hooks were the probe's gate at 1.3 ms at p50, and io-guard's own at 39.5 and 39.8 ms
  at p50, 45.2 and 44.0 ms at p95. The probe server's own time per call, from its log, was 0.5 ms in every run.
- `launch-exec` of 13:32 and `launch-pyrun` of 13:29 carried the same second hook, at 40.5 and 40.1 ms at p50,
  so their rows in `docs/launcher.md` were mixed too.

Run again on 2026-09-28 from 18:04 UTC, one probe at a time, with io-guard off, and the desktop app open with
this session:

| Probe | Release | p50 | p95 | Max |
|---|---|---|---|---|
| `launch-mcp` | 2.1.283 | 1.2 ms | 1.6 ms | 5.2 ms |
| `launch-mcp` | 2.1.281, the desktop's | 1.2 ms | 1.4 ms | 5.2 ms |
| `launch-exec` | 2.1.283 | 54.5 ms | 58.2 ms | 62.8 ms |
| `launch-pyrun` | 2.1.283 | 300.5 ms | 307.9 ms | 313.3 ms |

Not run: the desktop app closed, and after a reboot. Neither was needed once the second hook explained the
number, and the fast runs came with the app open.

- Docs: `docs/launcher.md` (the table, 2.1.281, and what io-guard's checks add), `docs/live-checks.md` (the
  row, both releases), `docs/compat.md` (the fallback's numbers), `docs/design/architecture.md` (the
  per-turn hook, about 300 ms), `.claude/tasks/context.md` (the cause).
- No code changed, and no test: the fix was `without_installed()`, already in `run_probe.py`.
- `live-empty` and `live-answers` timed 1.8 to 46.9 ms over 9 calls. Both run io-guard's own pipeline in the
  hook, the same work as the 39.5 ms above, so their range is not the hook path's.
