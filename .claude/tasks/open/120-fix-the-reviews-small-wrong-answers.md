---
title: Fix the small wrong answers the code review found
stage: I
area: mcp
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: small wrong answers from the code review"
---

## Why

The code review of 2026-09-29 found these, each small and each on its own:

1. **The settings page drops a non-ASCII token.** `mcp/dashboard_http.py` `hmac.compare_digest` raises
   `TypeError` for a non-ASCII `X-IOGuard-Token`, rerun on 2026-09-29, and the connection drops with a
   traceback instead of a 403. Slice C item 14.
2. **A long run's error lines count from the wrong place.** For a log over `shell.results.max_bytes`,
   `mcp/tools_run.py` `reading` numbers the error lines from the start of the tail it read, not the file, so
   they disagree with `io.read_log`. Slice C item 15.
3. **Every PermissionError is "another program holds it open".** `mcp/in_place.py` says so for any
   `PermissionError`, and on macOS a folder with no write permission gets that reason. Slice C item 17.
4. **A Read that was too large reads the whole file to count lines.** `checks/diagnose.py` `too_large`: a
   157 MB log peaked at 314 MB. Slice A item 17.
5. **The session probe can lose another plugin's lines.** `checks/session_probe.py` `add_lines` reads
   `CLAUDE_ENV_FILE`, adds its lines and replaces the file, with no lock, so a concurrent SessionStart hook's
   lines can go. Slice A item 18.
6. **`PIPE_HIDES_EXIT` fired on a command that only printed files.** This session's Bash call
   `ls open; ls done | tail -5; cat done/$(ls done | grep '^96') | head -60` got `PIPE_HIDES_EXIT` quoting an
   `AssertionError` line from the task file it printed, on 2026-09-29. `cat` and `head` read, and the grep
   sits in a command substitution.
7. **A generator's own write is told to use io.edit next time.** `python tools/skill.py`, which this
   repository's CLAUDE.md names as the way to write the skill's tables, got `SHELL_WRITE: tools/skill.py
   changed plugins/io-guard/skills/io-guard/SKILL.md, which git tracks, so those writes skipped io-guard's
   byte checks and Claude Code's checkpoints. Make the next change to them with
   mcp__plugin_io-guard_io__io_edit or the Edit tool.` on 2026-09-29. A file a script regenerates is changed
   by running the script again, never by hand.

## What to build

1. Compare bytes, and answer 403 to a token that is not ASCII.
2. Add the tail's starting line to each error line number.
3. Name a holder only when `holders()` finds one. Otherwise say the file or its folder cannot be written.
4. Count lines by streaming the file in blocks.
5. Append io-guard's lines to the env file, and write none it already holds.
6. A command substitution's commands count as readers when they are, so a pipe of readers stays quiet.
7. The scripted-write warning names the script as the way to change the file again, not an edit tool.

## Where

`mcp/dashboard_http.py`, `mcp/tools_run.py`, `mcp/in_place.py`, `checks/diagnose.py`,
`checks/session_probe.py`, `checks/command_results.py`.

## Done when

- A test per item.
