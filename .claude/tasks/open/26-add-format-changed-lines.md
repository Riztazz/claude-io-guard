---
title: Format only the changed lines
stage: F
area: mcp
created: 2026-09-27
status: open
depends-on: [15, 23]
findings: [BYT-3, BYT-11, BYT-12]
platforms: [windows, macos]
commit: "feat: run the formatter over changed hunks only, in the file's own endings"
---

## Why

clang-format over a whole file re-indents untouched code and adds namespace closers. CLICKER agents wrote two
scripts to work around it:
- `fmt_hunks.py`, run 128 times
- `unformat.py`, to revert what the formatter changed

A fixed `LineEnding: CRLF` on an LF file left mixed endings (BYT-3).

## What to build

`io.format(paths[], formatter?)`. It works in three steps:
1. Find the changed line ranges with `git diff -U0` through `lib.git`. Take the whole file when it is untracked, or
   the ranges the call gives.
2. Run the formatter over those ranges only, with `clang-format --lines` or the formatter configured for the
   extension.
3. Check the result against the file's profile before writing it, inside `lib.locks.file_lock`.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_format.py`, `tests/mcp/test_tools_format.py`.

## Done when

- A sample of CLICKER files gives the same output as `fmt_hunks.py`. The script is described in
  `baseline/io_traps.html`, and its copy sits in CLICKER's scratchpad if it still exists.
- A file keeps its ending style whatever the formatter config says.
