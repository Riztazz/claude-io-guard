---
title: Small cleanups and modernizations from the shell review
stage: I
area: lib
created: 2026-10-01
status: open
depends-on: [166, 167]
findings: []
platforms: [windows, macos]
commit: "refactor: small cleanups in the shell checks"
---

## Why

Fable's review of 2026-10-01, item 13 and simplifications S5, S11, S14 to S17 and S19. Each is small.

- "pipefail" is a substring test in three places: `echo "pipefail" | grep x` reads as if pipefail were set.
  `checks/lint.py` `hidden_exit` and `checks/command_results.py` `hiding_pipe` also judge "a build piped into a
  filter" two ways.
- The `halved(span)` closure is written twice, in `checks/lint.py` and `checks/transport_body.py`.
- `checks/command_results.py` splits the error text by hand where `str.partition` reads plainer.
- `lib/output.py` makes plurals by hand while `checks/command_results.py` has `plural()`.
- `lib/writes.py` `inside_folder` splits a path with a regex where `PureWindowsPath(...).name` does it.
- `lib/shell.py` slices `text[at:]` for a regex at every redirect, which grows with the square of a long
  command's redirects.
- Modernizations: the scanner's states as an `IntEnum`, `Scanner.pair` as one compiled pattern,
  `itertools.pairwise` in `lib/portable.py`, `match` in `rules.unwrapped` and `writes.in_place`, and
  `slots=True` on the small frozen dataclasses.

## What to build

Each item above, one at a time, with the suite green after each.

## Where

`lib/shell.py`, `lib/output.py`, `lib/writes.py`, `lib/portable.py`, `lib/rules.py`, `checks/lint.py`,
`checks/command_results.py`, `checks/transport_body.py`.

## Done when

- One `piped_into` and one pipefail test on blanked text, both checks calling them, and the rest done or
  each one named here as not worth it.
