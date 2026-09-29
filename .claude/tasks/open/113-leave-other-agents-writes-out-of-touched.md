---
title: Leave another agent's writes out of the files a command changed
stage: I
area: checks
created: 2026-09-29
status: open
depends-on: []
findings: [GIT-7]
platforms: [windows, macos]
commit: "fix: shell.touched names only what the command itself changed"
---

## Why

Found on 2026-09-29, during the code review. The main session wrote `README.md`, `docs/settings.md` and
`docs/tools.md` with the Write tool while three review subagents ran read-only commands. The subagents were
told by `TOUCHED_BY_SHELL` that their commands had changed those files, and two of them said so in their
reports. `shell.touched` compares git status before and after the command, so any write in that window counts
as the command's, whoever made it.

## What to build

- `shell.touched` leaves out a file that the session's journal, or the session's own Edit, Write or io tool
  calls, wrote between the command's PreToolUse and its PostToolUse.
- A shell command of another agent in the same window still counts. The message says "changed while this
  command ran" rather than "this command changed" when another call of the session overlapped it.
- A test with a Write recorded inside a Bash call's window.

## Where

`checks/touched.py`, `lib/journal.py`, `lib/context.py` (`SessionState`).

## Done when

- The test's Write is not named, and `live-touched` still passes.
