---
title: Make the file lock take turns, so a busy process cannot starve another's io tool
stage: I
area: lib
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: io-guard's file lock takes turns between processes"
---

## Why

CI on the Windows runner failed on 2026-09-29, 961 tests, 1 failure:

```
FAIL: test_two_processes_editing_one_file_both_land (tests.mcp.test_tools_edit.CallsOnOneFileTakeTurns...)
AssertionError: Tuples differ: ([0, 1], b'A=40\nB=0\n') != ([0, 0], b'A=40\nB=40\n')
... ioguard.mcp.toolspec.ToolFailure: Another io-guard call held a.txt for 5 seconds, so io.edit wrote nothing.
```

`lib/locks.py` `file_lock` polls a lock file every `RETRY_S` (20 ms). A process that edits in a loop takes
the lock again at once after it lets go, so a waiter polling on its own clock rarely catches the gap. Measured
the same day on Windows with each edit slowed by 30 ms inside the lock: the order the 80 edits landed in was
40 of A, then 40 of B. B got the lock only once A was done, and on the slower runner A's 40 edits took more
than 5 seconds, so B gave up. Locally the test passed 6 times in 6 at 0.6 s, which hid it.

## What to build

- A waiter that misses the lock marks that it wants it, in a file beside the lock file, and keeps the mark
  fresh while it waits. A process about to take the lock steps aside for one retry when another process's
  mark is fresh. The waiter clears its mark once it holds the lock.
- A test that the two processes' edits interleave, and the existing test passes on both runners.

## Done when

- With each edit slowed inside the lock, the order alternates between the processes, and CI is green.

## What changed

- `lib/locks.py`: `file_lock` writes the process id to `<name>.want` beside the lock file on each retry it
  waits, through `write_atomic`, and clears the mark once it holds the lock, if the mark is still its own.
  Before its first try, a process steps aside for two retries when `wanted_by_another` finds another
  process's mark younger than `WANT_S` (0.2 s). A process that died while waiting leaves a mark that goes
  stale on its own.
- Docs: `docs/design/architecture.md` (Hold the file). The README states nothing this changed.

Evidence:

- Measured with each edit slowed by 30 ms inside the lock, 40 edits per process: before, the order was 40 of
  A then 40 of B. After, `BABABABABABABABABABBAABABB...`, with both at 40.
- `python tests/run_all.py`: 964 tests, OK, up from 962. New: two processes taking the lock 20 times each,
  30 ms inside, never run more than 4 turns in a row, and `wanted_by_another` makes way only for another
  process's fresh mark. `tests.lib.test_locks` and `tests.mcp.test_tools_edit` passed 5 runs in 5.
- Live, Claude Code 2.1.283 on Windows: `live-edit-parallel` passes (20260929-135344).

Checked on Windows 10 on 2026-09-29. Not checked: the CI runners, until the next push.
