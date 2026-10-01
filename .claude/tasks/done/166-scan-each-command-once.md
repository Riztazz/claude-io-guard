---
title: A Bash call is scanned 7 to 9 times per hook
stage: I
area: checks
created: 2026-10-01
status: done
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

## What changed

- `shell.scan` and `shell.commands` keep their result per command, with `functools.lru_cache(maxsize=64)`.
  Both return frozen values, so every check of one call shares them. The splitting itself moved to
  `shell.split`, which `commands` calls once per command.
- The `found` parameter is gone from `commands`, `blanked`, `pipelines` and `exit_candidates`, and from
  `writes.located`. It existed only to spare a second scan, which the cache now spares for every caller.
- `transport.body`'s second scan of an unmoved command now reads the cached one, so it needs no change.
- `bash_writes` drops exact duplicates. A python -c body is read by its program and by the scan, and the two
  readers each find bodies the other misses: the scan finds one inside `$()`, the program's reading one after
  `time` or `env`. So both stay and the second copy of a write goes.
- Not done: one `Host` in `commit.policy`. `Host.of(ctx)` builds a frozen value from three fields already on
  the context, so building it five times costs nothing worth a change.

Evidence:

- `test_every_check_on_one_bash_call_shares_one_scan_and_one_split` in `tests/lib/test_shell.py` failed first
  with 8 scans and 4 splits for one Bash PreToolUse through every check, and now counts 1 and 1.
  `test_a_python_c_body_names_each_target_once` in `tests/lib/test_writes.py` failed first with two writes.
- The checks' own time before a call, over 2,000 corpus Bash commands with a fake git, each with the cache
  cleared first: p50 2.36 ms, p90 3.87, p99 6.97 without the cache, and p50 1.42 ms, p90 2.07, p99 3.49 with
  it. A second run of each gave the same within 0.7 ms at p99. Task 156 measured a live Bash hook's p50 at 57
  to 128 ms, most of it git, so a live hook gains about 1 ms.
- `python tests/run_all.py`: 1,150 tests, OK, 2 skipped, against 1,148.

Docs: `docs/design/architecture.md` gives `scan`'s cache and the `commands` and `split` signatures.

Checked on Windows 10 on 2026-10-01.
