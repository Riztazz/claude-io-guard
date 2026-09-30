---
title: Split the three functions that do several jobs
stage: I
area: runtime
created: 2026-09-29
status: done
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

## What changed

Validated on 2026-09-30 before building. All three functions were as described, with two updates: task 129
moved `bash_writes` to `lib/writes.py:143`, 43 lines, and task 130 had already replaced the `SimpleCommand` it
built with `program_name`. The rebinding of `edited` by a walrus was still there.

- `lib/writes.py`: `bash_writes` walks the commands and gathers the bodies and script files.
  `command_writes(simple, where, cwd, host, depth)` returns one simple command's writes, `delegated_writes` the
  files `find -exec` or `xargs` edits in place, and `run_words` the program's words once. Each case returns,
  so `edited` has one meaning.
- `checks/touched.py`: `changes(before, event, ctx)` returns a frozen `Changes` record, the read, changed,
  created, deleted and moved paths, with `status_changes` sorting what git status lists anew. `summary(changes,
  binary, cwd, scratchpad, limit, tool, platform)` renders the record into TOUCHED_BY_SHELL, and
  `Touched.report` joins the two with the byte drift and the script check. `diffed` became a module function.
- `checks/command_results.py`: `Reading.__init__` reads the command, the exit code and what the call printed,
  through `printed`. The saved file, its text, the whole output and the error lines are lazy properties,
  worked out when a reader first asks.

Tests first:

- `test_the_split_functions_stay_short` in `tests/test_layout.py`: no function in the four modules is over 40
  lines. It failed on `report`, 77, and `bash_writes`, 43.
- `tests/lib/test_writes.py`: one command's writes for sed -i, find -exec, tee, a redirect, bash -c and ls.
- `TheReportRendersARecordOfChanges` in `tests/checks/test_touched.py`: a record renders on its own, and an
  empty one renders nothing.

The existing tests pass unchanged.

Docs: none. `architecture.md` lists no function of the three modules this changes.

Evidence, on Windows on 2026-09-30:

- The suite: 1,094 tests, 1,090 before, OK with 2 skipped.
- A replay over the corpus with HEAD's code and with this change: 7 checks, shell.writes and shell.results
  among them, 0 differences. The replay sends no PostToolUse to shell.touched, so its counts are the probes'
  to show.
- Live, Claude Code 2.1.283, from this checkout: `live-touched`, `live-touched-move` and `live-touched-index`
  (the report), `live-refuse` and `live-script-write` (the write finder), `live-results` and `live-pipe-once`
  (the shell result) pass.
