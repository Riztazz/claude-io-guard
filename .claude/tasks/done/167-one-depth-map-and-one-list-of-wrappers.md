---
title: Four walks count parentheses and three lists name the wrapper words
stage: I
area: lib
created: 2026-10-01
status: done
depends-on: [164]
findings: []
platforms: [windows, macos]
commit: "refactor: one depth map and one wrapper list for shell commands"
---

## Why

Fable's review of 2026-10-01, simplifications S2, S3, S6, S7, S12 and S13.

- Four walks count `$()` and `( )` depth: `Scanner.normal`, `word_end`, `structure()` and `subshells()`.
- Three lists of wrapper words disagree: `shell.RESERVED` (time, exec, command, builtin, nohup, sudo),
  `rules.unwrapped` (time, nohup, builtin, noglob, command, timeout, nice, stdbuf, xargs) and
  `writes.without_env`. Task 164's python -c miss after `time` and `env` comes from this.
- `ASSIGNMENT` is defined three times, in two spellings, in `lib/shell.py`, `lib/writes.py` and
  `lib/rules.py`.
- `commands()` emits an arithmetic word as a command, and `lib/rules.py` carries `ARITHMETIC` only to filter it.
- `word_end`'s branch for a `(` at its start cannot be reached, and one `states[at] == NORMAL` test repeats.

## What to build

- The Scanner writes the depth at each offset, and the other three read it.
- `commands()` keeps words as written, and every reader unwraps through one function.
- One `ASSIGNMENT`, in `lib/shell.py`.
- `commands()` drops an arithmetic word, and `rules.ARITHMETIC` goes.

## Where

`lib/shell.py`, `lib/rules.py`, `lib/writes.py`.

## Done when

- HEAD against the new code over the corpus gives the same checks' results, or each difference is named here.

## What changed

- **One depth map.** Task 164 gave `Scan.closes` and moved `word_end` onto it. Here the scanner also records
  where an unquoted `${ }` ends, and `structure()` and `subshells()` step over each expansion by `closes`
  instead of counting parentheses themselves. Both now take the `Scan`. A case pattern's `)` inside a `$()`
  no longer closes a subshell around it.
- **One declaration of the words before a program.** `lib/shell.py` holds `RULE_WRAPPERS` (time, nohup,
  builtin, noglob), `WRAPPERS` (those and exec, command, sudo), `KEYWORDS`, `RESERVED` as keywords and
  wrappers, and `ASSIGNMENT`. `rules.unwrapped` reads `RULE_WRAPPERS` and `shell.ASSIGNMENT`, `writes`
  reads `shell.ASSIGNMENT`, and the python -c regex's command start is built from `WRAPPERS`. The two copies
  in `lib/rules.py` and `lib/writes.py` are gone.
- Not done: one stripping step for every reader. `rules.unwrapped` keeps stripping only what Claude Code
  strips before it matches a permission rule, since stripping `sudo` there would deny a command Claude Code
  itself lets through. So the stages stay, and only the word lists became one.
- **`(( ))` alone is no command.** `split` drops a command's first word when it is arithmetic, so
  `rules.ARITHMETIC` and the filter that used it are gone.
- `split` reads its own `normal` flag twice where it tested `states[at] == NORMAL` again. `word_end`'s
  branch for a `(` at its start went with task 164's rewrite.

Evidence:

- `test_a_subshell_holds_past_a_case_pattern_inside_its_substitution` failed first: the old code put `cd sub`
  in group 0, outside its subshell. `test_arithmetic_on_its_own_runs_no_command` failed first with a command
  named `(( i++ ))`.
- Over the corpus's 58,779 Bash commands, against HEAD: `scan` and `commands` give the same result for every
  one. `structure` differs on 2, both a case pattern inside `$()`, which the old walk took as the
  substitution's end. `subshells` differs on 34, each with a `( )` inside a `$()`, which the old walk counted
  as a group. Only top-level commands read those ids, and none sits inside a `$()`, so only later groups'
  numbers shift.
- Full replay, HEAD against this change: no check's decision differs.
- `python tests/run_all.py`: 1,164 tests, OK, 2 skipped, against 1,162.

Docs: `docs/design/architecture.md` gives `subshells`' signature and the word lists.

Checked on Windows 10 on 2026-10-01.
