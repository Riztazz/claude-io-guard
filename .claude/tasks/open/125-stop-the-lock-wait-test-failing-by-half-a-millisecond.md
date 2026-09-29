---
title: Stop the lock wait test failing by half a millisecond on Windows CI
stage: I
area: lib
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows]
commit: "fix: file_lock waits at least the time it was given"
---

## Why

The lead's CI run on 2026-09-29, the Windows runner, 1,010 tests:

```
FAIL: test_a_second_holder_waits_and_then_times_out (tests.lib.test_locks.OneHolderOfAFileLockAtATime.test_a_second_holder_waits_and_then_times_out)
  File "D:\a\claude-io-guard\claude-io-guard\tests\lib\test_locks.py", line 75, in test_a_second_holder_waits_and_then_times_out
    self.assertGreaterEqual(waited, 0.2, "it waits the time it was given first")
AssertionError: 0.19947809999999322 not greater than or equal to 0.2 : it waits the time it was given first
```

`lib/locks.py` waits on Windows with `WaitForSingleObject(event, round(wait_s * 1000))`, line 190. That wait
counts in the system timer's ticks, about 15.6 ms by default, while the test measures with `time.monotonic()`,
which reads the performance counter. The two clocks disagree by a fraction of a tick, so the kernel wait can
end 0.5 ms before `monotonic` says 0.2 s has passed. The failure depends on the runner's timer, so it passes
on the lead's machine and fails now and then on CI.

## What to build

- `file_lock` waits at least `wait_s` by `time.monotonic()`: after the kernel wait times out, it waits again
  for what is left, until the monotonic deadline has passed. The contract then holds on any timer, and the
  test keeps its exact bound.
- Check the POSIX path, the flock in a helper thread, for the same early return.

## Where

`lib/locks.py` (the Windows wait at line 190, and the POSIX wait), `tests/lib/test_locks.py`.

## Done when

- The test's bound holds on the Windows runner across several CI runs, with no tolerance added to it.
