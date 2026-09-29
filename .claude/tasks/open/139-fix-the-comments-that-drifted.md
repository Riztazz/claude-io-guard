---
title: Fix the comments that no longer match the code, and the glued lines
stage: I
area: runtime
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "docs: comments say what the code does now"
---

## Why

Low. Five comments describe a rule the code no longer keeps, and seven lines are shaped in a way no other line
in the package is. The `prose` skill: check every claim against the body, and a comment that is wrong is
worse than none.

Comments that drifted:

- `plugins/io-guard/scripts/ioguard/lib/retention.py:23-24`, `older`: "None when folder does not exist", and
  the body returns `[]` at line 26.
- `plugins/io-guard/scripts/ioguard/checks/session_probe.py:5-6`: "Only the user sets the defaults, never a
  project, because a variable such as PYTHONSTARTUP or BASH_ENV runs a program (D24)". D38 replaces D24's rule
  for project files, and the keys at lines 122-125 carry `project_may_set=False, runs=True`, which is the rule
  now.
- `plugins/io-guard/scripts/ioguard/mcp/tools_format.py:8`: "The command comes from the format key in the
  user's own config.json, clang-format by default for C and C++ (D24)". Under D38 a project's file names it
  too, once approved through `io.trust`, and `plan` at line 168 reads the merged config.
- `plugins/io-guard/scripts/ioguard/mcp/handles.py:7-8`: "Task 32's snapshot handles add a file each, which
  outlives the server", and line 21: `kind: str  # "run", and later "snapshot"`. `mcp/tools_history.py` never
  calls `handles`, and a snapshot's id comes from `lib/snapshots.py:57`.
- `plugins/io-guard/scripts/ioguard/checks/shell_writes.py:17-18`: a wrap that leaves "A" alone at the end
  of line 17 and starts line 18 with "stream redirect". `checks/conform_write.py:10-11` leaves "hooks.answer
  leaves" and `checks/commit_policy.py:10-11` leaves "An" the same way.

Lines shaped like no other:

- `plugins/io-guard/scripts/ioguard/lib/rules.py:53`: `UNREAD_BASH =("$(", "`", "<(", ">(")`, no space
  before the parenthesis. `lib/rules.py:60`: `MANAGED = {"win32":Path(...)`, no space after the colon.
  `mcp/tools_edit.py:24`: `HASH_DOC =(`.
- `plugins/io-guard/scripts/ioguard/lib/rules.py:45-48`: `PWSH_VALUED` wraps with `"-v",` alone on line 47.
- `plugins/io-guard/scripts/ioguard/lib/shell.py:530-531`: `QUOTED_PATH_BEFORE_QUOTE` sits on the line after
  `script_run`'s `return`, with no blank line between a function and a constant.
- `plugins/io-guard/scripts/ioguard/checks/diagnose.py:51-52`: `PART_BYTES = 60_000` sits on the line before
  `@dataclass(frozen=True)`, the same way.
- `plugins/io-guard/scripts/ioguard/checks/heartbeat.py:76-77`: two blank lines end the file.

## What to build

- Each comment says the rule that holds now, in the present tense. The `handles` docstring and the `kind`
  comment name only the run handle, or say that a kind is a string the tool that makes it chooses.
- The wraps and the spacing follow the lines around them.

## Where

`lib/retention.py`, `checks/session_probe.py`, `mcp/tools_format.py`, `mcp/handles.py`,
`checks/shell_writes.py`, `checks/conform_write.py`, `checks/commit_policy.py`, `lib/rules.py`,
`mcp/tools_edit.py`, `lib/shell.py`, `checks/diagnose.py`, `checks/heartbeat.py`.

## Done when

- A grep of `plugins/io-guard/scripts` for `D24` finds nothing.
- Each comment named above matches its body on a read-through.
- The suite passes, since no code changes.
