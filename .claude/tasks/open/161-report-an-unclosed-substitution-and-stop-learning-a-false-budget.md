---
title: The scanner misses an unclosed $(, so a malformed command teaches a false Bash budget
stage: I
area: lib
created: 2026-10-01
status: open
depends-on: [159]
findings: []
platforms: [windows]
commit: "fix: an unclosed $() is unterminated and teaches no budget"
---

## Why

Fable's review of 2026-10-01, items 2 and 3.

- `Scan.unterminated` is False for `echo $(foo`, `echo $(echo a # x)`, `echo ${x` and an unclosed backtick.
  Bash stops on each with "unexpected EOF while looking for matching `)'". `Scanner.substitution()` runs
  `normal()` to the end of the text and records nothing when the `)` never comes.
- `shell.results`' `budget()` in `checks/command_results.py` trusts that verdict. A command over 5,000 bytes
  that bash rejects as malformed reads as one the Bash tool cut, so the session learns a false budget and
  refuses every later command over it with TRANSPORT_BUDGET. Fable drove both `echo $(echo a # x) yyyy...`
  and a CR quote command of 5,138 bytes through the pipeline, and each set `budget_override`. The corpus holds
  98 EOF failures over 5,000 bytes that the scanner calls well-formed, not yet sorted into real cuts and
  malformed commands.

## What to build

- `Scanner.substitution()` sets `unclosed` when no `)` closes it, and an unclosed backtick does the same.
- `budget()` also needs `not found.carriage_returns` before it learns from a command.
- The TRANSPORT_BUDGET message says the Bash tool cut the command only when the scan found nothing malformed.

## Where

`lib/shell.py` `Scanner.substitution()` and the backtick handling, `checks/command_results.py` `budget()`.

## Done when

- The four shapes above are unterminated, and neither of Fable's two long commands sets `budget_override`.
- The 98 corpus failures are counted again, split into cuts and malformed commands, and the count goes in
  this file.
