---
title: Fix the small wrong answers the code review found
stage: I
area: mcp
created: 2026-09-29
status: done
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

## What changed

Each item's test failed first, for the reason named.

1. `mcp/dashboard_http.py`: `allowed` compares the token as bytes, so a token with U+00E9 gets 403. Before, the
   `TypeError` dropped the connection (`tests/mcp/test_tools_dashboard.py`).
2. `mcp/tools_run.py`: `reading` adds the line breaks before the tail it read, counted by
   `lib.context.newlines` in 1 MB blocks. A run printing 2,000 lines, then `ValueError`, with `max_bytes` 500,
   names the error on line 2001, where it said 45 (`tests/mcp/test_tools_run.py`).
3. `mcp/in_place.py`: `write_refused` names a holder only when `holders()` finds one, as `FILE_LOCKED`, and
   otherwise gives `READ_ONLY`: the system refused the write, no program holds the file, and the file or its
   folder cannot be written. `io.restore` in `mcp/tools_history.py` made the same guess, `Another program
   holds ... open`, and now calls it too (`tests/mcp/test_tools_edit.py`).
4. `checks/diagnose.py`: `too_large` takes the size from `stat` and counts lines with `newlines`, never
   reading the file whole. The test watches reads of the large file only, since `FakeFs.read_tail` reads the
   transcript whole, and it failed on HEAD with a whole read of the file (`tests/checks/test_diagnose.py`).
   `FakeFs.read_from` now slices its bytes rather than reading the file through `read_bytes`.
5. `checks/session_probe.py`: `add_lines` appends through the new `FsPort.append`, `lib.bytesio.append` in one
   write. A line another hook adds between io-guard's read and its write is kept
   (`tests/checks/test_session_probe.py`). The offline `DryFs` keeps an append in memory.
6. `checks/command_results.py`: `ls` and `dir` join `READERS`. The task's guess was the command substitution,
   but `cat done/$(ls done | grep '^96')` stays one word, and the two `ls` calls were what made the command
   more than reading. The recorded command now gets nothing (`tests/checks/test_command_results.py`).
7. `checks/touched.py`: when no file the script changed is among its arguments, the script wrote it unasked,
   and the fix reads `Change SKILL.md by changing tools/skill.py or what it reads, then run it again.` A
   script given the file, such as `python fmt.py b.cpp`, keeps the io.edit advice (`tests/checks/test_touched.py`).

- The suite of 1,044 passes on Windows, 2 skipped. Each run prints two `ConnectionResetError` tracebacks from
  an older page server test, filed as task 127.
- `live-probe`, `live-script-write` and `live-results` passed on the CLI 2.1.283.
- Docs: `docs/design/architecture.md` (`FsPort.append`, `READ_ONLY` for a refused write with no holder).
- Checked on Windows on 2026-09-29.
