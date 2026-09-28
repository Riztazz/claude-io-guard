---
title: Fit the report's lines to its width, and count the info codes
stage: I
area: infra
created: 2026-09-28
status: open
depends-on: [28]
findings: []
platforms: [windows, macos]
commit: "fix: keep the report's lines whole, and count its info codes"
---

## Why

`python tools/report.py --days 1` on 2026-09-28 printed `Calls: PreToolUse 1,096, ..., PostToolUseFa` and
`Projects: ..., and 4 `. `render` cuts every line at `WIDTH`, 110 characters (`cli/report.py`, line 175), and
the `Calls`, `Tools` and `Projects` lines come from `listed`, which does not fit its names to that width. Only
the line after the code table goes through `fitted`, which keeps whole names.

The same run showed `EXIT_BENIGN` as 0, 0 and 0. The table has a column for fixed, warned and refused, and an
info code falls in none of them, so a code that fired reads as one that never did.

## What to build

- The `Calls`, `Tools` and `Projects` lines go through `fitted`, or a helper both share, so no line ends in the
  middle of a name.
- An `info` column, or the info codes counted under a name that says what they are.
- Tests: a report with more names than fit, and one with an info code.

## Where

`plugins/io-guard/scripts/ioguard/cli/report.py`, `tests/cli/`.

## Done when

- Every line of the report ends on a whole name or a count, and `EXIT_BENIGN` shows the number of times it fired.
