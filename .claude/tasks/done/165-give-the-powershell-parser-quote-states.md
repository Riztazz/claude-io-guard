---
title: The PowerShell parser misreads nested quotes and here-string closes
stage: I
area: lib
created: 2026-10-01
status: done
depends-on: [160]
findings: []
platforms: [windows, macos]
commit: "refactor: the PowerShell parser keeps a state per character"
---

## Why

Fable's review of 2026-10-01, item 14 and simplification S18.

- An indented `'@` is taken as a here-string close. PowerShell rejects it with a parse error, and accepts only
  an unindented close. Fable ran both.
- `"a $('b'.Replace("b","c")) d"` runs in PowerShell, printing `a c d`, but `quoted_end` ends the string at the
  inner `"`. The rest reads as code, and `blanked()` shows string text to the read-only and kill rules.
- `commands()` and `blanked()` each find `#` comments and walk quotes on their own.

## What to build

A state per character, as `lib/shell.py` keeps for Bash, built once. `blanked()` reads it, `commands()` reads
it, and a reader that moves one character on anything it does not take cannot hang, as task 160's did.

## Where

`plugins/io-guard/scripts/ioguard/lib/pwsh.py`, `tests/lib/test_pwsh.py`.

## Done when

- Both shapes above read as PowerShell reads them, and the corpus's 3,321 PowerShell calls give the same
  results as before, or each difference is named here.

## What changed

- `pwsh.scan(command)` walks the command once and gives each character a state: `CODE`, `STRING` for a
  string or here-string with its quotes, or `COMMENT`. It keeps its result per command, as `shell.scan` does.
- `commands`, `word_at` and `blanked` read those states. `commands` no longer finds comments itself, and
  `word_at` steps over a string by its state instead of calling `quoted_end`. `script_blocks` reads
  `blanked`, so it shares the walk too.
- `quoted_end` closes a here-string only at the start of a line, and steps over a `$( )` inside a
  double-quoted string with `subexpression_end`, so the code's own quotes never close the string.
- Task 160's guard stays: `commands` steps past a `)`, `]` or `}` that closes nothing.

Evidence:

- `test_a_here_string_closes_only_at_the_start_of_a_line`,
  `test_a_subexpression_keeps_its_own_quotes_inside_a_string` and
  `test_one_walk_gives_every_reader_its_states` in `tests/lib/test_pwsh.py` failed first. The
  subexpression test passed on the old code until it checked every word `blanked` leaves, which showed `b` and
  `c` from the string read as code.
- Over the corpus's 3,321 PowerShell calls, against HEAD: one splits differently and one blanks differently.
  The split is a fix: a `#` comment holding `aren't` inside a `foreach` block used to open a string, so the
  block ran to the end of the command. It now closes at its `}`, and the commands after it are read.
- Full replay, HEAD against this change: no check's decision differs.
- `python tests/run_all.py`: 1,162 tests, OK, 2 skipped, against 1,159.
- The indented `'@` rule is Fable's PowerShell run from 2026-10-01. It was not run again here.

Docs: `docs/design/architecture.md` lists `pwsh.scan`.

Checked on Windows 10 on 2026-10-01.
