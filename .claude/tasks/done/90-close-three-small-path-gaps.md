---
title: Close three small path gaps: relative command paths, device names in io writes, and io.format off-project
stage: I
area: lib
created: 2026-09-29
status: done
depends-on: [81]
findings: [security-review-2026-09-29-10, security-review-2026-09-29-11]
platforms: [windows, macos]
commit: "fix: io-guard's commands and writes stay on the paths they name"
---

## Why

Fable's security review of 2026-09-29, findings 10 and 11, low, checked in the code the same day.

- `lib/proc.py` runs a program named with a folder as given, and `checks/verify_command.py` runs in the
  session's folder. A user's `verify` or `format` entry such as `tools/check.exe` therefore runs from whatever
  repository is open.
- `mcp/in_place.py`, which `io.edit`, `io.splice` and `io.append` write through, never calls `paths.reserved`,
  so they lack `write.location`'s refusal of Windows device names such as `nul`.
- `mcp/tools_format.py` applies the project's `format` entry to a file outside the project, where the hooks use
  `Context.for_file` to keep one project's config off another's files.

## What to build

- `lib/commands.py` `command_problem` accepts a program as a bare name or an absolute path, and refuses a
  relative one, naming the fix.
- `in_place` refuses a reserved device name as `write.location` does.
- `io.format` takes `ctx.for_file(path)` for each file.
- Tests for each.

## Done when

- Each of the three is refused or scoped as described, with a test.

## What changed

- `lib/commands.py`: `command_problem` refuses a program that names a folder without being absolute on
  either platform (`relative`), naming the fix: its absolute path, or its bare name for PATH. The module
  docstring no longer says only the user's file may hold the keys, which D38 made wrong.
- `mcp/in_place.py`: `load` refuses a Windows device name with `RESERVED_NAME`, so `io.edit`, `io.splice`,
  `io.append` and `io.format` all refuse it before touching the file.
- `mcp/tools_format.py`: `plan` and the waiting notice take `ctx.for_file(path)` for each file.
  `lib/context.py`: `Context.for_file` also empties `held` for a file outside the project, so no project's
  waiting command is named for it.
- Docs: `docs/design/architecture.md` (commands, `for_file`, in_place) and `README.md`, whose verify section
  also said a project file cannot name a command, wrong since task 80.

Evidence:

- `python tests/run_all.py`: 951 tests, OK, up from 948. New: `tools/check.exe` and `..\bin\lint.cmd` are
  refused as relative, and a bare name, drive paths, a POSIX path and a UNC path pass. `io.edit` and
  `io.append` on `nul.txt` answer `RESERVED_NAME` and write nothing. `io.format` on a file in another
  repository finds no command although the project's config names one, and names no waiting command.
- The lead's own `verify` is `["python", "-m", "py_compile", "{file}"]`, a bare name, so it still loads.

Checked on Windows 10 on 2026-09-29. Not checked live: these are refusals of arguments, which the unit tests
reach through the tools themselves. macOS in task 36.
