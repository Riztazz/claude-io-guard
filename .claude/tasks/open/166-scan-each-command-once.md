---
title: A Bash call is scanned 7 to 9 times per hook
stage: I
area: checks
created: 2026-10-01
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "perf: each command is scanned once per hook"
---

## Why

Fable's review of 2026-10-01, simplifications S1, S4, S8, S9 and S10, and item 16.

`shell.scan(command)` runs about 7 to 9 times and `commands()` about 6 times per Bash PreToolUse: twice in
`transport.body`, twice through `lib/writes.py`, twice in `shell.lint`, once in `win.paths`, twice in
`commit.policy`, and three more in `shell.touched` after the call. `commit.policy` also builds `Host.of(ctx)` five
times. `lib/writes.py` reads a python -c body twice and reports each target twice. Task 156 measured a Bash
hook's p50 at 57 to 128 ms, most of it git, so the gain is real but small.

## What to build

- One Scan per command per hook: a cache on `shell.scan`, which returns a frozen value, or a Scan carried
  on the Event.
- `transport.body` passes the Scan it already has to `as_it_runs()`.
- `commit.policy` builds one Host and passes one Scan down.
- `lib/writes.py` reads a python -c body once.

## Where

`lib/shell.py` `scan()`, `checks/transport_body.py`, `lib/writes.py`, `checks/commit_policy.py`,
`checks/touched.py`.

## Done when

- A count of `Scanner.run()` calls for one Bash PreToolUse is 1, in a test, and the hook's time before and
  after is in this file.
