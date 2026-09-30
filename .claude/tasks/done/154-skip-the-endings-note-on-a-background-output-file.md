---
title: Leave the mixed-endings note off a background command's output file
stage: I
area: checks
created: 2026-09-30
status: done
depends-on: [16]
findings: []
platforms: [windows, macos]
commit: "fix: give no endings note for Claude Code's own output files"
---

## Why

`read.profile` adds a note to every Read: the file's endings, encoding and indent. On a background Bash
command's output file it also warns that the file mixes line endings. In CLICKER on 2026-09-30 four Reads of
`%TEMP%/claude/<project>/<session>/tasks/<id>.output` each got, for example, `io-guard: mixed endings, UTF-8,
2 spaces, 36 lines` and `io-guard: The file mixes line endings: 34 CRLF and 2 LF.` The CRLF lines are what the
program printed, and the LF lines are the two Claude Code adds, such as `[exited with code 0]`. Nobody edits
that file, so the warning asks for attention and leads nowhere. An empty one reads `no endings, UTF-8, 0
lines`, which says nothing either.

## What to build

- A Read of a file under Claude Code's own session folder, `tasks/*.output` beside the scratchpad, gets no
  profile note and no mixed-endings warning.
- A test with one such path, and one with a project file that mixes endings, which still gets the warning.

## Where

`plugins/io-guard/scripts/ioguard/checks/read_profile.py`, `lib/profile.py:126`, where the warning is written,
`tests/checks/`.

## Done when

- A Read of a background command's output file gets no io-guard line, and a project file that mixes endings
  still gets both.

## What changed

`lib/output.is_task_output` tells the file by its path alone: an `.output` file in a `tasks` folder whose parent
folder is named for the session's id. `read.profile` returns before it reads such a file, so the Read gets no
line and no warning. The session keeps no profile of it either, so no later check compares the file, which
grows while the task runs, with what the agent read.

The session id is in the path, so a project's own `tasks/b1.output` still gets its line and its warning. So does
another session's output file, which this session has no reason to read.

Evidence:

- Two tests failed first. `test_only_an_output_file_in_the_sessions_tasks_folder_is_one` in
  `tests/lib/test_output.py` has six paths. In `tests/checks/test_read_profile.py`,
  `test_a_background_tasks_output_file_gets_no_line_and_a_project_file_still_does` reads the same mixed bytes
  at both paths.
- `python tests/run_all.py`: 1,138 tests, OK, 2 skipped, against 1,136 at task 153.
- The path's shape was read off the disk: `%TEMP%/claude/<project>/<session>/tasks/<id>.output`, in five session
  folders on 2026-09-30.
- Not seen live: a Read of a real output file with the new code loaded. The installed plugin is the old one
  until it is updated and the session restarts.
- macOS: the path test runs in CI. The folder Claude Code uses there was not seen, and the rule reads only the
  last three parts of the path.

Docs: `docs/design/architecture.md` lists `is_task_output` and the check's new case. No setting, tool or drawing
changed.

Checked on Windows 10 on 2026-09-30.
