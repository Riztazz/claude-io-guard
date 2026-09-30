---
title: Fix the comments that no longer match the code, and the glued lines
stage: I
area: runtime
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "style: comments and layout match the code"
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

## What changed

Three items no longer held, since earlier tasks had fixed them:

- `checks/shell_writes.py:17-18`: task 129 rewrapped the docstring when it moved the write finder to
  `lib/writes.py`.
- `checks/diagnose.py:51-52`: task 129 put the two blank lines before `@dataclass` when it moved the diagnosis to
  `lib/diagnosis.py`.
- `lib/rules.py:60`: `MANAGED` reads `{WINDOWS: Path(...)` since task 133 keyed it by `Platform`.

The rest held, with lines moved. What changed:

- `lib/retention.py`, `older`: the docstring says an empty list when the folder does not exist, which is what
  the body returns.
- `checks/session_probe.py`: the defaults are the user's own config's alone, never a project's file, and a
  write of them through `io.config` waits for the user's yes (D38, D40), in place of D24.
- `mcp/tools_format.py`: the command comes from the format key, and one a project's `.claude/io-guard.json`
  names runs only once the user approves it through `io.trust` (D38), in place of D24. `untrusted` in
  `lib/waiting.py` is what holds it back.
- `mcp/handles.py`: the docstring drops the snapshot handles, since only `mcp/tools_run.py` imports the
  module, and the `kind` comment says it is the tool's own name for the work, `"run"` for `io.run`.
- `checks/conform_write.py` and `checks/commit_policy.py`: the glued wraps are one paragraph again.
- `lib/rules.py`: `UNREAD_BASH = (`, and `PWSH_VALUED` wraps with no word alone on a line.
  `mcp/tools_edit.py`: `HASH_DOC = (`, which lines up with its second line again.
- `lib/shell.py`: two blank lines between `script_run` and `QUOTED_PATH_BEFORE_QUOTE`.
  `checks/heartbeat.py`: ends with one newline.

The test: `ModulesAreLaidOutAlike` in `tests/test_meta.py` scans every Python file in `plugins`, `tests` and
`tools` for a top-level definition with fewer than two blank lines to its neighbour, and for a file that does
not end with exactly one newline. It failed on `checks/heartbeat.py` and `lib/shell.py:532` first, the only
two in the repository, then passed. Its second test shows it finds a constant glued to a function and a blank
line at the end, in a built source. The spacing inside a line, such as `=(`, has no test: Python's tokenizer
reads both spellings the same, and a scan of the text for it would be a formatter.

Evidence:

- `grep -rn D24 plugins/io-guard/scripts --include=*.py` finds nothing.
- No Python line in `plugins`, `tests` or `tools` is over 110 characters.
- `python tests/run_all.py`: 1,103 tests, OK, 2 skipped, against 1,101 at task 138.
- `live-empty`, `live-server`, `live-results`, `live-format` and `live-trust` passed on the CLI 2.1.283.

Docs: none needed. The comments were the stale copy, and the design doc already names D38 and D40.

Checked on Windows 10 on 2026-09-30. macOS is covered by CI only.
