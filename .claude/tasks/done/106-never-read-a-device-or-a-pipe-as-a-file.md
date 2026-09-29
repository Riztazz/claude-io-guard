---
title: Never read a device or a pipe as a file, and answer a path the system rejects with a refusal
stage: I
area: lib
created: 2026-09-29
status: done
depends-on: []
findings: [PTH-5]
platforms: [windows, macos]
commit: "fix: io-guard answers a device, a pipe or a bad path with a refusal"
---

## Why

The code review of 2026-09-29: slice C item 3 and slice A item 15. Task 90 refused Windows device names on the
write path only. The read path opens them:

- `lib/bytesio.py` `read_bytes` of `proj/CON` from a process with no console and a piped stdin blocked for
  more than 5 s, rerun on Windows on 2026-09-29. `COM1` and `AUX` do the same. The tool handler cannot be
  cancelled, and four such calls fill the default four workers and stall every hook.
- `io.read`, `io.snapshot`, `io.compare`, `io.run`'s script reads, `shell.writes`' script reads and
  `commit.policy`'s `-F` file read all open the path they are given. `python /dev/stdin` makes `shell.writes`
  read `/dev/stdin`, which on macOS is the server's own stdin. A FIFO blocks the same way, and `/dev/zero`
  reads without end, since `stat` gives size 0.

Folded in from task 112 on 2026-09-29, since both need the same check on a path before it is opened or
stat-ed. The code review, slice C item 11 and slice B item 14: `lib/context.py` `LiveFs.stat` catches only
`FileNotFoundError`. On Windows a name holding `?`, `*`, `"`, `|` or a NUL, or one longer than 255 characters,
raises `OSError` WinError 123, and on macOS a path through a file raises `NotADirectoryError`. `io.read`,
`io.edit` and `write.location` then fail with `GUARD_ERROR`. `io.run` does the same for a NUL in argv, a `=`
in an environment key, and a lone surrogate in `code`. The one `GUARD_ERROR` of 2026-09-29's report came from
`stat` on a path task 98 now leaves unread.

## What to build

- `LiveFs.stat` answers `None` for any `OSError` that means the path cannot exist, and logs the reason.
- `io.run` checks its argv, env and code before it starts anything, and refuses a bad one with
  `INVALID_ARGUMENTS` naming the field.

- One `lib` function, beside the device-name check task 90 put in `in_place.load`, says whether a path is a
  regular file that is safe to open: not a reserved Windows name, and `S_ISREG` after `stat`. Every read of a
  path that came from a tool call or a command goes through it, and a path that fails is `PATH_NOT_FOUND` or
  skipped, with the reason.
- Tests: `CON`, `COM1` and `AUX` on Windows, and a FIFO and `/dev/zero` on macOS, each answered at once.

## Where

`lib/bytesio.py`, `lib/paths.py`, `lib/context.py` (`LiveFs.stat`), `mcp/in_place.py`, `mcp/tools_read.py`,
`mcp/tools_history.py`, `mcp/tools_run.py`, `checks/shell_writes.py`, `checks/commit_policy.py`.

## Done when

- Each device and pipe case answers within 100 ms, on both CI runners.
- Each bad path and argument gets `PATH_NOT_FOUND` or `INVALID_ARGUMENTS`, never `GUARD_ERROR`.

## What changed

- `lib/bytesio.py`: `regular(path)` raises `OSError` for anything `stat` does not call a regular file, and
  `read_bytes`, `read_from` and `read_tail` open only what it passes. On Windows `stat` gives `CON`, `COM1`,
  `AUX` and `nul` as character devices, measured on 2026-09-29, so one check covers them, a FIFO and
  `/dev/zero`. Every read of a path a call or a command names goes through `ctx.fs` and so through it:
  `io.read`, `io.snapshot`, `io.compare`, the script files `shell.writes` reads, and a commit's `-F` file.
  The reads that bypass it open io-guard's own files: sessions, the journal and telemetry.
- `lib/context.py`: `LiveFs.stat` answers `None` for the errors no file can answer, `ENOENT`, `ENOTDIR`,
  `EINVAL` and `ENAMETOOLONG`, and still raises the others, such as a permission error.
- `mcp/tools_run.py`: `unrunnable` refuses, with `INVALID_ARGUMENTS`, a NUL in argv or in an env name or value,
  a name that is empty or holds `=`, and code UTF-8 cannot write.
- Tests, each failing first: `CON` read from a process with no console blocked past its 10 s limit, and a
  FIFO on macOS is the same test; `?`, a 300-character name and a path through a file each raised from
  `stat`; the three `io.run` inputs each raised `ValueError` or `UnicodeEncodeError`. All pass now, and the
  suite of 1,001 passes on Windows with 2 skipped.
- `live-empty` passed on the CLI 2.1.283, so ordinary reads still work.
- Docs: `docs/design/architecture.md` (`regular`, `read_bytes`, `stat`).
- Checked on Windows on 2026-09-29. The FIFO case runs on the macOS CI runner.
