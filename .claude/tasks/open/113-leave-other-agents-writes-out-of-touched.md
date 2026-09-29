---
title: Leave another agent's writes out of the files a command changed, and fit the advice to what it did
stage: I
area: checks
created: 2026-09-29
status: open
depends-on: []
findings: [GIT-2, GIT-7]
platforms: [windows, macos]
commit: "fix: shell.touched names only what the command changed, with advice that fits"
---

## Why

Found on 2026-09-29, during the code review. The main session wrote `README.md`, `docs/settings.md` and
`docs/tools.md` with the Write tool while three review subagents ran read-only commands. The subagents were
told by `TOUCHED_BY_SHELL` that their commands had changed those files, and two of them said so in their
reports. `shell.touched` compares git status before and after the command, so any write in that window counts
as the command's, whoever made it.

Folded in from task 123 on 2026-09-29, since both change the same message. `python tools/skill.py` rewrote
`plugins/io-guard/skills/io-guard/SKILL.md`, a tracked file the agent had not read, and `git mv` moved a task
file into `done/`. Each got `TOUCHED_BY_SHELL: This command changed <file>. Delete any new file the task does
not need, and keep the rest on purpose.` Neither command made a new file. `checks/touched.py` picks one advice
line for the whole result: read again when a changed file was read, else the delete advice when anything was
changed, created or deleted, else use the new paths. A changed file the agent never read falls into the delete
branch, which only fits a created one.

## What to build

- `shell.touched` leaves out a file that the session's journal, or the session's own Edit, Write or io tool
  calls, wrote between the command's PreToolUse and its PostToolUse.
- A shell command of another agent in the same window still counts. The message says "changed while this
  command ran" rather than "this command changed" when another call of the session overlapped it.
- A test with a Write recorded inside a Bash call's window.
- The advice follows each kind the command did, and says nothing for a kind it did not do: read files, read
  again. Created files, delete the ones the task does not need. Moved files, use the new paths. A changed
  file the agent never read needs no advice, since the agent's view of it is not stale. A test per kind, and
  one with a changed unread file alone.

## Where

`checks/touched.py` (the parts and the advice line), `lib/journal.py`, `lib/context.py` (`SessionState`).

## Done when

- The test's Write is not named, and `live-touched` still passes.
- The `SKILL.md` case reads `This command changed plugins/io-guard/skills/io-guard/SKILL.md.` with no delete
  advice.
