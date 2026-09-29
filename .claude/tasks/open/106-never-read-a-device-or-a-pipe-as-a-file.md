---
title: Never read a device or a pipe as a file
stage: I
area: lib
created: 2026-09-29
status: open
depends-on: []
findings: [PTH-5]
platforms: [windows, macos]
commit: "fix: io-guard never reads a device or a pipe as a file"
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

## What to build

- One `lib` function, beside the device-name check task 90 put in `in_place.load`, says whether a path is a
  regular file that is safe to open: not a reserved Windows name, and `S_ISREG` after `stat`. Every read of a
  path that came from a tool call or a command goes through it, and a path that fails is `PATH_NOT_FOUND` or
  skipped, with the reason.
- Tests: `CON`, `COM1` and `AUX` on Windows, and a FIFO and `/dev/zero` on macOS, each answered at once.

## Where

`lib/bytesio.py`, `lib/paths.py`, `mcp/in_place.py`, `mcp/tools_read.py`, `mcp/tools_history.py`,
`mcp/tools_run.py`, `checks/shell_writes.py`, `checks/commit_policy.py`.

## Done when

- Each device and pipe case answers within 100 ms, on both CI runners.
