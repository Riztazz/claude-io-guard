---
title: Say nothing about an Edit that changes nothing
stage: I
area: stale
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [20]
findings: []
platforms: [windows, macos]
commit: "fix: leave a no-op Edit to Claude Code's own error"
---

## Why

An Edit whose `old_string` equals its `new_string` got `STALE_VIEW` in CLICKER twice on 2026-09-28. Its message
said the file "needs no change there", and then gave the code's generic fix, "Read the file again, then change
only what differs". The two sentences disagree. The file was current, and nothing was left to do.

`STALE_VIEW` says the file holds something other than what the call expected, which is false here. Claude Code's
own error already says the whole of it: "No changes to make: old_string and new_string are exactly the same".

## What to build

- `diagnose.failure` answers that error with no result, before any other branch reads it. The `identical` flag
  of `stale` and its message go (`checks/diagnose.py`, lines 112, 113 and 202 to 204). The module docstring's
  sentence about it goes too.
- The other choice is a code of its own that asks for nothing. It adds a code for what Claude Code already
  says, so this task does not take it.
- Turn `test_identical_strings_show_the_text_already_there` into a test that the failure gives no result.

## Where

`plugins/io-guard/scripts/ioguard/checks/diagnose.py`, `tests/checks/test_diagnose.py`.

## Done when

- An Edit with equal strings gets Claude Code's error and nothing from io-guard.

## What changed

- `checks/diagnose.py`: the `IDENTICAL` constant, the `identical` flag of `stale` and its message are gone. No
  branch of `Diagnosis.results` matches "No changes to make", so it answers with no result. The module docstring
  says so.
- `tests/checks/test_diagnose.py`: `test_identical_strings_get_only_claude_codes_own_error` replaces the old test.
  `test_an_edit_refused_after_the_file_changed_shows_the_lines_as_they_are_now` covers `stale`, which the old test
  was the only one in the file to reach.
- `tools/probes/run_probe.py`: `live-diagnose` no longer expects `STALE_VIEW` from its step 8, the no-op Edit.
  `no_op_left_alone` passes only when Claude Code refused that Edit and no io-guard context about it reached the
  model.
- Docs: `docs/live-checks.md`, whose `live-diagnose` row is split in two and dated. No other doc named the no-op
  diagnosis.
- Evidence: `python tests/run_all.py` ran 811 tests, all passing, up from 810 by the one new test.
  `live-diagnose` passes on 2.1.281, the desktop app's own, and on 2.1.283, the CLI.
- Checked on Windows on 2026-09-28. The macOS live check waits in task 36.
- The report after the task named two more bugs, filed as tasks 56 and 57.
