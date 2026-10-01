---
title: Bash shapes the scanner and commands() misread
stage: I
area: lib
created: 2026-10-01
status: open
depends-on: [161]
findings: []
platforms: [windows, macos]
commit: "fix: the scanner reads here-strings, loops and wrapped python -c"
---

## Why

Fable's review of 2026-10-01, items 9, 10, 11, 12 and 15. Each is low harm, and each misleads every check
that reads the command after it.

- A here-string reads as an input redirect: `cat <<< "foo bar"` gives words ('cat', 'bar') and inputs
  ('foo',). The corpus holds 44 here-strings, 29 read this way, all of which ran.
- `python -c` after `time`, `then`, `do`, `env` or `exec` gets no compile check and no move:
  `time python -c "print(1)"` and `env FOO=1 python -c 'print(1)'` find no body. 140 of the corpus's 8,760
  python -c calls have no body found. The body regex has its own idea of where a command starts.
- Loop heads become commands: `for f in a b; do ...` gives a command named `f`, and `for ((i=0;...))` one
  named `((i=0;...))`, which `lib/rules.py` filters with a pattern of its own.
- A `case` pattern's `)` inside `$()` closes the substitution early.
- A quote inside `${...}` inside double quotes ends the string: `echo "${x:-"a b"}"` gives two words.
- `arithmetic()` marks the whole `$(( ))` as ARITH after scanning the `$()` inside it, so `blanked()` hides
  that command from kills and lint. Plausible, by reading.

## What to build

One fix per shape, each with a test from Fable's command, and a corpus count before and after.

## Where

`lib/shell.py`: `heredoc_word_end`, the redirect loop in `commands()`, `COMMAND_START` and `PYTHON_C`,
`commands()`' handling of `for`, `case` in `normal()`, `double()` and `${`, and `arithmetic()`.

## Done when

- Each shape above reads as bash reads it, and HEAD's scanner against the new one over the corpus differs
  only on these shapes.
