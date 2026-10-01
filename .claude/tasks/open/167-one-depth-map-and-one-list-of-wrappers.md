---
title: Four walks count parentheses and three lists name the wrapper words
stage: I
area: lib
created: 2026-10-01
status: open
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
