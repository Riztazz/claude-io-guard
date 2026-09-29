---
title: Make the file lock wait in the kernel, so a release hands it to the waiter
stage: I
area: lib
created: 2026-09-29
status: done
depends-on: [95]
findings: []
platforms: [windows, macos]
commit: "fix: io-guard's file lock waits in the kernel, first come first served"
---

## Why

Task 95 made a polled lock take turns through a `.want` mark file. The lead read it as timing luck, and asked
Fable, whose review of 2026-09-29 found it unsound: a waiter's mark can land between the holder's check and
its take, three waiters overwrite one mark, a `write_atomic` every 20 ms can itself be slowed past the holder's
cycle by Defender, `WANT_S` trusts mtimes that some filesystems round to seconds, and two threads of one
server share a pid, since `lib/context.py` `first_in_file`, `lib/trust.py` and `mcp/tools_dashboard.py` call
`file_lock` without the thread table. macOS CI then failed task 95's own test:

```
FAIL: test_two_processes_that_take_the_lock_in_a_loop_take_turns (tests.lib.test_locks...)
AssertionError: 5 not less than or equal to 4 : a waiter gets the lock between the other's turns:
ABBABABBABBABABAABBBAAAAABBAAABBABBBABAA
```

## What to build

- `lib/locks.py` `file_lock` waits in the kernel with a timeout, and no longer polls. Windows: `LockFileEx`
  on an overlapped handle, `WaitForSingleObject` with the timeout, `CancelIoEx` when it passes, and an unlock
  if the lock landed as the cancel arrived. The lock manager grants pending waiters in order. macOS: a
  blocking `fcntl.flock` in a helper thread, given up at the timeout, which releases the lock if it lands
  later. A holder that dies loses its lock with its handle on both.
- Delete the `.want` mark, `wanted_by_another`, `read_or_none`, `WANT_S` and the poll.
- Tests that do not rest on a fairness count: a busy re-locker cannot keep a waiter out, a dead holder frees
  the lock, and a waiter that timed out leaves nothing held. Drop the turns-in-a-row test. The two-process
  edit test waits 30 s per call, since it proves serialisation, not the timeout.

## Done when

- The lock tests pass on both CI runners, and the two-process edit test lands 40 and 40.

## What changed

- `lib/locks.py`: `file_lock` takes the lock through `windows_lock` or `posix_lock` and gets back the function
  that lets it go. `windows_lock` opens the lock file with `CreateFileW` and `FILE_FLAG_OVERLAPPED`, asks
  `LockFileEx` for its first byte, waits on the request's event with `WaitForSingleObject` up to `wait_s`,
  and past it cancels with `CancelIoEx` and unlocks if the lock landed as the cancel arrived. `posix_lock`
  tries `flock` without blocking, then blocks in a `PosixWait` helper thread, which the caller gives up on at
  `wait_s`. A lock that lands after that is let go at once, and the thread closes the descriptor.
  `wait_s=0` takes the lock only if it is free. The `.want` mark, `wanted_by_another`, `read_or_none`,
  `WANT_S`, `RETRY_S`, `locked` and `unlocked` are gone.
- Every caller keeps its `TimeoutError`, so `in_place.held` still answers `FILE_LOCKED`. The callers without
  the thread table, `first_in_file`, `trust.approve` and the settings writer, now serialise their threads
  too, since each call opens its own handle and the kernel sees two holders.
- `tests/lib/test_locks.py`: the turns-in-a-row test and the want-mark test are gone. New: a busy holder
  keeps a waiting process out for at most a few turns, and on Windows the waiter is strictly first; a holder
  that dies frees the lock; a waiter that timed out leaves nothing held. `tests/mcp/test_tools_edit.py`: the
  two-process edit test's children wait 30 s per call, since it proves serialisation, not the timeout.
- Docs: `docs/design/architecture.md` (Hold the file). The README states nothing this changed.

Evidence:

- The same measurement as task 95, 40 edits per process with 30 ms inside the lock, on Windows:
  `ABABABABAB...` for all 80, strict turns.
- The busy-holder test's scenario run against the old polled lock from c46e104 put B 6th of 51, so its
  cross-platform bound of 10 would pass there too. Only the Windows assertion, B first, tells the locks
  apart. macOS `flock` keeps no queue, so the macOS claim is a bound, as Fable's review said.
- `python tests/run_all.py`: 965 tests, OK. `tests.lib.test_locks` and `tests.mcp.test_tools_edit` passed 5
  runs in 5. Live, Claude Code 2.1.283: `live-edit-parallel` passes (20260929-140720).

Checked on Windows 10 on 2026-09-29. Not checked: the macOS branch, which cannot run on Windows since
`fcntl` does not exist there. Its first run is the macOS CI runner after the push.
