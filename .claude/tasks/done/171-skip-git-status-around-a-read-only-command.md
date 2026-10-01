---
title: Skip git status around a Bash command that can change no file
stage: I
area: checks
created: 2026-10-01
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "perf: skip git status around a read-only command"
---

## Why

The performance pass of 2026-10-01. `shell.touched` runs `git rev-parse` and `git status` before every Bash
call and `git status` again after it. Timed through the real hook entry on real files, 15 rounds:

| Project | PreToolUse Bash | PostToolUse Bash |
|---|---|---|
| CLICKER | 71.9 ms | 54.5 ms |
| claude_io_guard | 36.3 ms | 20.9 ms |

`git status --untracked-files=all` alone takes 56 ms in CLICKER and 19 ms here. A command that only reads,
such as `ls`, `grep`, `git log` or `sed -n`, can change no file, so both runs tell the agent nothing.

## What changed

- `lib/readonly.py`, new: `only_reads(command, readers)` is True when every simple command reads, by
  `READERS`, nothing goes to a file but `/dev/null`, and bash runs nothing the words hide. A `$()` or a
  backtick that bash runs, in code, in double quotes, in a heredoc body or in arithmetic, makes the command a
  writer, since `shell.commands` keeps a substitution inside its word: `X=$(rm a) && ls` reads as `ls` alone.
  A reader told to write is a writer: sed with `-i` or a `w` or `e` command, find with `-delete` or `-exec`,
  `sort -o`, `uniq` with an output file, and `--output`. git is matched by its subcommand, past `-C` and the
  other options. A command the scan cannot read to its end is never read-only.
- `checks/touched.py`: a Bash `PreToolUse` that only reads keeps no snapshot, so neither git status runs and
  the `PostToolUse` finds nothing to compare. The list is the new setting `checks.shell.touched.readers`, and
  a project's list replaces it. PowerShell is watched as before.
- Tests: `tests/lib/test_readonly.py`, three tests over 13 readers and 26 writers, and
  `test_a_read_only_command_runs_no_git_status` in `tests/checks/test_touched.py`. All failed first.
- Docs: `docs/design/architecture.md` (the package tree), `docs/settings.md` (the new setting).

Evidence:

- The replay cannot judge this change: it records no git status, so `shell.touched` gives nothing in it
  before or after. Its 18 codes are equal.
- Telemetry instead, every session on this machine: 84 `TOUCHED_BY_SHELL` on Bash. One command is called
  read-only from its telemetry head, which stops at 200 characters. Its whole command in the transcript runs
  `mv`, and `only_reads` says False on it. So the change loses none of the 84.
- Share of telemetry Bash calls skipped: CLICKER 15.7% of 337, SmartTablesHost 23.2% of 427, this repository
  44.0% of 1,913. On the replay corpus, by the same rule, 35 to 47% per project.
- Timed again on CLICKER, `git log --oneline -3`: PreToolUse 71.9 to 1.2 ms, PostToolUse 54.5 to 1.0 ms.
- `python tests/run_all.py`: 1,171 tests, OK, 2 skipped, against 1,167.

Checked on Windows 10 on 2026-10-01.
