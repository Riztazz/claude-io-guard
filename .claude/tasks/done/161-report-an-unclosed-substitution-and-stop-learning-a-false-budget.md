---
title: The scanner misses an unclosed $(, so a malformed command teaches a false Bash budget
stage: I
area: lib
created: 2026-10-01
status: done
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

## What changed

- `Scanner.normal()` marks the scan unclosed when it reaches the end inside a `$(`, at any depth, which also
  covers a `#` that comments out the `)`. An odd number of unescaped backticks, outside or inside double quotes,
  marks it unclosed too.
- `budget()` in `checks/command_results.py` learns only from a command with no `Scan.carriage_returns` as well,
  so a CR quote Git Bash rejects is never taken for a cut.

Not built: an unclosed `${`, as in `echo ${x`. The scanner has no reading of `${...}` at all yet, and task 164
takes `${` up for its quoting bug, so the two land together there.

Evidence:

- `test_a_substitution_or_backtick_left_open_is_unterminated` in `tests/lib/test_shell.py` holds 5 open and 6
  closed shapes, and `test_a_command_bash_could_never_parse_teaches_nothing` in
  `tests/checks/test_command_results.py` holds an unclosed `$(`, a commented `)`, an open backtick and a CR
  quote, each over 6,000 bytes. Both failed first. A scratch script ran the 11 shapes through Git Bash 5.2.37:
  each open one stopped with "unexpected EOF", and no closed one did.
- Over the corpus's 58,779 Bash calls, against HEAD's scanner, 2 commands newly read as unterminated, and both
  had failed. No call that ran changed.
- The 98 recorded EOF failures over 5,000 bytes still all read as well-formed. Their sizes run from 7,807 to
  25,559 bytes, and the smallest command the Bash tool cut, per task 35, is 7,807 bytes. So all 98 are real
  cuts, and none is a malformed command the budget learned from.
- `python tests/run_all.py`: 1,146 tests, OK, 2 skipped, against 1,144.

Docs: `docs/design/architecture.md` says what well-formed means for the budget, and what `Scan.unterminated`
covers.

Checked on Windows 10 on 2026-10-01.
