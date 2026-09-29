---
title: Make every pattern a project or an input reaches run in linear time
stage: I
area: lib
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: no pattern or line io-guard reads can stall its server"
---

## Why

The code review of 2026-09-29: slice A item 2, slice B item 6, slice C item 12. Python's `re` cannot be
interrupted and holds the GIL, so one slow match stalls the io server's hooks for every call. Measured on
Windows on 2026-09-29:

| Pattern | Input | Time |
|---|---|---|
| `lib/text.py` `TRAILING`, `[ \t]+$` with `re.M` | 10,000, 20,000 and 40,000 spaces, then `x` | 0.38, 1.48 and 5.46 s |
| `lib/shell.py` `BODY_FILE`, from `shell.writes` and `shell.lint` | `echo` of one 10 KB and 20 KB token | 0.51 and 2.04 s for the whole check |

Reported by the reviewers and not rerun: `lib/patterns.py` `nested()` accepts `(a|aa)+b` and
`\d+\d+\d+\d+\d+\d+X`, which grow exponentially and as n^6. `lib/rules.py` turns a permission pattern such as
`a*a*a*a*a*a*a*a*b` into `.*` joins, which grows as n^8 on every `io.run`. `lib/editorconfig.py` globs such as
`*a*a*a*b` are unbounded. macOS has no 8 KB Bash cut, so a base64 blob in one command reaches all of them.

## What to build

- `TRAILING`: strip each line's end with `rstrip`, no regex.
- `BODY_FILE`: an atomic group or a possessive quantifier, which Python 3.11 and later have, so the token
  scan cannot backtrack.
- `patterns.nested()`: also refuse an alternation under a repeat, and two adjacent repeats of classes that
  overlap. A project's pattern that fails is dropped with the config message, as now.
- `rules.matches` and `editorconfig.matches`: a wildcard matcher of their own, two pointers with one
  backtrack point, in linear time, in place of a regex.
- A test per row, each under 50 ms on 100 KB of input.

## Where

`lib/text.py`, `lib/shell.py`, `lib/patterns.py`, `lib/rules.py`, `lib/editorconfig.py`.

## Done when

- Each input above takes under 50 ms at 100 KB, and the existing tests pass.
