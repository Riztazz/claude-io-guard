---
title: Say nothing about an Edit that changes nothing
stage: I
area: stale
created: 2026-09-28
status: open
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
