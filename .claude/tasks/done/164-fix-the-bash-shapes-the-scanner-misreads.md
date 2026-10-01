---
title: Bash shapes the scanner and commands() misread
stage: I
area: lib
created: 2026-10-01
status: done
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
- An unclosed `${`, as in `echo ${x`, does not read as unterminated. Task 161 left it here, since the scanner
  needs a reading of `${...}` for both.
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

## What changed

All in `lib/shell.py`.

- **Here-strings.** The scanner steps over `<<<`, so `<<` no longer reads as a heredoc there, and `split`
  drops the here-string's word: it goes to stdin, and is no argument and no input file.
- **python -c after a keyword or a wrapper.** `COMMAND_START` takes `time`, `then`, `do`, `else`, `exec`,
  `env`, `nohup`, `command`, `builtin` and `!` before the program. Task 167 still merges the three wrapper
  lists into one.
- **Loop heads.** `for` and `select` stay first in their head, so the head is named for its keyword and never
  for its variable. The values stay words. A first version dropped the head whole, and the replay showed
  `win.paths` losing 56 of its 166 fixes, such as `for p in /Game/...; do python editor.py ... $p`, where the
  path reaches python as `$p`. Keeping the words restored all 166.
- **case inside `$()`.** `normal` counts `case` and `esac` inside a substitution, and a `)` that closes no `(`
  while a case is open ends a pattern, not the substitution.
- **`${ ... }`.** `parameter` reads an expansion to its matching `}`, with its quotes and `$()`. In double
  quotes its own characters stay part of the string, so `"${x:-"a b"}"` is one word. An expansion left open
  makes the scan unterminated, which task 161 had left here.
- **`$(( ))`.** `arithmetic` marks only its own characters ARITH, so a command inside keeps its states and
  `blanked` shows it.
- **One end for each `$()`.** The scanner records where each `$()` and `$(( ))` ends in `Scan.closes`, and
  `word_end` jumps there instead of counting parentheses a second time. That is what made the case fix work
  in `split`, and it is the first part of task 167's single depth map.
- **An open quote inside `$()`.** `single` and `ansi` return at most the command's length. One recorded
  command, a `'` left open inside a `$()` inside a string, sent `word_end` past the end and crashed
  `split`. The corpus diff found it, and `test_a_quote_left_open_inside_a_substitution_ends_the_last_word`
  holds its shape. That test was written after the fix, since the crash showed up first in the corpus.

Evidence:

- 7 new tests in `tests/lib/test_shell.py`, `ShapesBashReadsItsOwnWay`, failed first, 12 failures in all.
- Git Bash 5.2.37 ran the here-string, the case pattern, the quote inside `${}`, both open `${`, and the
  command inside `$(( ))`, and each result matched what the tests expect.
- HEAD's scanner against this one over the corpus's 58,779 Bash commands: 3,920 commands scan or split
  differently, all from these shapes. 3,889 hold a loop head, 49 a `$(( ))`, 31 a here-string, 2 a wrapped
  python -c, 1 a `${`, and the last is a loop head after an operator the sorting pattern missed.
- Full replay, HEAD against this change: no check's decision differs, on any command.
- `python tests/run_all.py`: 1,159 tests, OK, 2 skipped, against 1,152.

Docs: `docs/design/architecture.md` describes `Scan.closes` and the shapes in `scan`'s entry.

Checked on Windows 10 on 2026-10-01.
