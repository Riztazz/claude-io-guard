---
title: Find why an mcp_tool hook now takes 38 ms where it took 1.2 ms
stage: I
area: launch
created: 2026-09-28
status: open
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
