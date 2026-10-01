---
title: The PowerShell parser misreads nested quotes and here-string closes
stage: I
area: lib
created: 2026-10-01
status: open
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
