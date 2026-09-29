---
title: Cap a background run's log
stage: I
area: mcp
created: 2026-09-29
status: open
depends-on: []
findings: [RUN-4]
platforms: [windows, macos]
commit: "fix: a background run's log stops at a cap"
---

## Why

The code review of 2026-09-29, slice C item 16, split out of task 105. A background `io.run` keeps running
when its session's io server stops: `lib/proc.py` `Pump.stop` runs only on a timeout or a cancel, and task
105's stop cancels only the calls still waiting for an answer, which a background run is not. Its log in
io-guard's `runs/` folder has no size cap, so a run that prints without end fills the disk until
`io.saved_days` deletes it.

## Already decided

`docs/design/architecture.md`, section 8, says a background run keeps running past the server's end, and its
log stays in io-guard's folder. That stays unless the lead says otherwise. The gap is the log.

## What to build

- A run's log stops growing at `io.run.log_max_bytes`, 64 MB by default, a user setting, and the run's last
  `io.status` says the log was cut.
- A test for the cap.

## Where

`lib/proc.py`, `mcp/tools_run.py`, `mcp/server.py`, `lib/config.py`.

## Done when

- A run past the cap keeps its first 64 MB and says so.
