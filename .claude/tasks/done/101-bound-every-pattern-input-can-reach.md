---
title: Make every pattern a project or an input reaches run in linear time
stage: I
area: lib
created: 2026-09-29
status: done
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

## What changed

- `lib/text.py`: `visible` marks trailing spaces line by line through `trailing_marked`, an `rstrip`, and the
  `TRAILING` regex is gone.
- `lib/shell.py`: `BODY_FILE` starts a match only where a token starts, a lookbehind, so a long token is
  scanned once.
- `lib/wildcard.py`, new: `match(pattern, text, fold)`, a `*` pattern met with one backtrack point, the last
  star, at most the text's length times the pattern's. `lib/rules.py` `matches` uses it in place of the `.*`
  regex, with the same meaning, a trailing ` *` also meeting the bare command.
- `lib/editorconfig.py`: `glob_pattern` and its regex are gone. `alternatives` expands `{a,b}`, nested, to at
  most 256 globs, `tokens` turns each into steps, and `covers` marks the offsets each step can end at, so a
  match costs the steps times the path's length. A `{` with no `}` is a plain character, and an empty or
  backward class holds nothing, which also ends task 117's three globs that raised.
- `lib/patterns.py`: `nested` also refuses a repeated group that holds a `|` choice, and `problem` refuses a
  pattern with more than `OPEN_REPEATS` (2) open repeats, counted by `open_repeats`. Every pattern the lead's
  four projects set still passes.
- Tests, each shown failing first against the old code with a time limit: 100,000 spaces then text in
  `visible` failed its 0.5 s bound, a 100 KB token in `body_files` took 54.8 s, the 8-star rule on 5,000
  characters and the 8-star glob on 250 ran past 60 s, and `(a|aa)+b` and `(?:x|y)*z` passed the guard. Each
  now takes milliseconds, and the suite of 987 passes on Windows. A glob test covers nested braces and `**/`.
- Task 97's replay over 62,100 recorded commands gives the same rule decisions with the new matcher: 8 deny,
  5 ask, 672 and 55 unread.
- Not done: a pattern with two open repeats can still cost the square of a line's length, and `error_lines`
  runs the patterns over each whole line. A line cap there would bound it, and is left for when a real line
  shows the cost.
- Docs: `docs/design/architecture.md` (the package tree and the signatures), `docs/settings.md` (the pattern
  rule), the `lib/patterns.py` docstring.
- Checked on Windows on 2026-09-29. macOS runs the same tests on CI.
