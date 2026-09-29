---
title: Split the three functions that do several jobs
stage: I
area: runtime
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: split touched.report, bash_writes and Reading"
---

## Why

Medium. Three functions each carry several jobs in one body, so a change to one job is made among the
others, and a test of one job runs all of them.

- `plugins/io-guard/scripts/ioguard/checks/touched.py:189-265`, `Touched.report`, is 77 lines. It compares
  the two snapshots, sorts paths into read, changed, created, deleted and added, pairs moves, then builds the
  message, its steps and its evidence, with two local functions inside. `shown_moves`, `parts` and `steps`
  are three chains of conditional list additions on the same five lists.
- `plugins/io-guard/scripts/ioguard/checks/shell_writes.py:131-172`, `bash_writes`, walks the simple
  commands and dispatches on seven shapes, then gathers heredoc bodies, inline bodies, moved bodies and script
  files, then reads writes out of each. At line 142 it builds a whole `SimpleCommand` to read one field:
  `name = shell.SimpleCommand(tuple(words), (), (), simple.span).name if words else ""`. `edited` is set at
  line 144 and bound again by a walrus at line 152 inside the `elif under is not None:` branch, so a reader
  has to hold two meanings of one name.
- `plugins/io-guard/scripts/ioguard/checks/command_results.py:114-139`, `Reading.__init__`, does the work of
  the class in the constructor: scans the command, reads the response or the error, checks the saved output's
  folder, reads the saved file, and matches the error patterns, so a test of `benign` or `garbled` runs all
  of it first.

## What to build

- `Touched.report` becomes a step that computes a small frozen record of the changes, read, changed, created,
  deleted and moved, and a step that renders that record into the result. Each is a function a test can call
  with the record alone.
- `bash_writes` becomes a per-command function that returns the writes of one simple command in its folder,
  and a function that gathers the bodies and scripts, with the program name read once through the helper
  `fable-name-a-program-once` adds. The walrus rebinding of `edited` goes.
- `Reading` keeps only the values it needs at construction, and computes the saved text and the error lines
  in named methods, or a builder function makes a frozen `Reading` from the event.
- The existing tests pass unchanged, since nothing a caller sees changes.

## Where

`checks/touched.py`, `checks/shell_writes.py`, `checks/command_results.py`, and their tests.

## Done when

- No function in the three modules is longer than 40 lines.
- The suite passes, and a replay over the corpus shows the same counts for `shell.touched`, `shell.writes`
  and `shell.results`.
