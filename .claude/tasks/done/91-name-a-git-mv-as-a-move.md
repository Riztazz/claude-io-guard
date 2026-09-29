---
title: Name a git mv as a move in TOUCHED_BY_SHELL, not as a deletion
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: io-guard names a file git moved as moved"
---

## Why

Task 82's report run, 2026-09-29. `git add <task file> && git mv .claude/tasks/open/82-... .claude/tasks/done/`
got `TOUCHED_BY_SHELL: This command deleted .claude/tasks/open/82-gate-command-writes-through-io-config.md.
Delete any new file the task does not need, and keep the rest on purpose.` The file was moved, not deleted,
and the advice about new files does not fit. Every task this repository finishes ends with a `git mv`, so the
message repeats with no effect.

## What to build

- `checks/touched.py` pairs a deletion with an added path git status reports as a rename (`R`), or with a new
  file of the same bytes, and names it as moved from one path to the other.
- A move asks for nothing, so the message is information only, or none when the command itself names `git mv`.
- Tests with a `git mv` into another folder, and with a plain `mv` of a tracked file.

## Done when

- A `git mv` gets no deletion warning, live through a probe or the lead's own sessions.

## What changed

- `checks/touched.py`: `moves` pairs a path that left with one that arrived: a rename git status names, or a
  path gone and a new or newly added one with the same file name, and the same size where the size before is
  known (a read or listed file), or a command that names a move where it is not. `names_a_move` finds `mv`,
  `git mv`, `Move-Item`, `ren` and their kin in a Bash or PowerShell command. A pair is left out of deleted,
  created and changed. When the command names a move, the pairs say nothing. Otherwise they are named as
  `moved a to b`, with "Use the files' new paths from now on." when nothing else changed. The evidence
  gains `moved`.
- `tools/probes/run_probe.py`: `live-touched-move`.
- Docs: `docs/design/architecture.md` (touched.py) and `docs/live-checks.md`. The README states nothing
  this changed.

Evidence:

- `python tests/run_all.py`: 960 tests, OK, up from 958. New: `git add` then `git mv` of a new file, `git mv`
  of a tracked file (a rename entry) and `mv` of a tracked file each report nothing, and a script moving a
  read file reports `This command moved open/a.md to done/a.md.`
- Live, Claude Code 2.1.283 on Windows: `live-touched-move` passes (20260929-133341). `git mv task.md done/`
  after a Read of task.md got no message, and `python mover.py` got `TOUCHED_BY_SHELL: This command moved
  notes.md to archive/notes.md. Use the files' new paths from now on.`

Checked on Windows 10 on 2026-09-29. Not checked: macOS (task 36).
