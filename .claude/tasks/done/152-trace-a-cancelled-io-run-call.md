---
title: An io.run cut short by a new user message comes back as an empty error, with no code
stage: I
area: mcp
created: 2026-09-30
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: the debug log shows each cancel and its debug lines"
---

## Why

Raised from SmartTablesHost on 2026-09-30, in a live session. A foreground `io.run` was under way when the lead
sent a new message. The call came back with nothing after the tool's name:

```
io.run  argv: ["python", "restyle_board.py"]
        cwd:  C:\Users\felia\AppData\Local\Temp\claude\...\scratchpad\music
        timeout_s: 120

Error calling tool (mcp__plugin_io-guard_io__io_run):
```

The same call, made again straight after, ran in 2.2 s and exited 0. So the script was fine, and the failure is
the call's. io-guard has a code for this case, `CANCELLED`: "The client cancelled the io tool call before it
finished." It did not arrive, and an agent reading an empty error cannot tell a cancel from a crash in io-guard.

That the new user message cancelled the call is inferred from the timing and not checked in the code.

## What to build

- A call the client cancels answers with `CANCELLED` and the call's argv, when the transport still lets io-guard
  answer at all.
- When it cannot answer, the debug log records the cancel with the call's handle, so the cause can be read later.

## Where

The io server's handling of a cancel notification during a foreground `io.run`. Not located in the code yet.

## Done when

- A test sends a cancel during a foreground `io.run` of a program that sleeps for 5 s, and reads back
  `CANCELLED` or a debug log line naming the cancel.

## What changed

Numbered 152 when it was picked up on 2026-09-30.

The report's main claim did not hold. io-guard never received the call, so it had nothing to answer. From
SmartTablesHost's transcript and io-guard's telemetry for that session, at 2026-09-30 05:12:06 UTC:

- .096, the model called `io.run`, tool use `toolu_015h3dHAuyW5EsX6MoGZiZ3e`.
- .104, io-guard's PreToolUse hook on the call answered, in 1.1 ms.
- .110, the lead's next message entered Claude Code's queue.
- .471, Claude Code wrote the result `Error calling tool (mcp__plugin_io-guard_io__io_run): `, empty.

Every `tools/call` that reaches an io tool writes a telemetry line, a `CANCELLED` or a `GUARD_ERROR` one
included, and none exists for that tool use. A protocol error would have carried its own message. So Claude Code
dropped the call between its PreToolUse hook and the request, and the empty text is its own.

A cancel that does reach the server answers `CANCELLED` already. This repository's own session holds two such
lines on 2026-09-30, `io.run` calls of 330 s and 160 s that Claude Code cancelled. The task's done-when test now
exists and passes on the code as it was: `test_a_foreground_io_run_cancelled_mid_run_stops_and_answers_cancelled`
in `tests/mcp/test_server.py` starts a real foreground `io.run` of a 5-second sleep through the server, cancels
it once its first progress notification goes out, and reads back `CANCELLED` in under 4 seconds.

Two gaps were real, and both are fixed:

- **A cancel left no trace.** `mcp/server.py` now logs each `notifications/cancelled` at debug level, with the
  request id, whether the server held a call for it, and the client's reason. A cancel for a call that never
  arrived then reads "which io-guard holds no call for". Its test failed first with no log line:
  `test_every_cancel_is_logged_with_whether_io_guard_held_the_call`.
- **No debug line ever reached `debug.log`.** `lib/telemetry.debug_log` added the file handler and left the
  `ioguard` logger at Python's default WARNING, so with `telemetry.debug` on the log held warnings and
  tracebacks, and none of the six `log.debug` lines in the package. It now lowers the logger to DEBUG.
  `test_a_debug_line_reaches_the_debug_log` in `tests/lib/test_telemetry.py` failed first with an empty file.
  `telemetry.debug`'s description says debug lines now, beside tracebacks.

Not built: an answer the client shows for a call it dropped before sending. No such answer can exist.

Evidence:

- `python tests/run_all.py`: 1,135 tests, OK, 2 skipped, against 1,132 at task 145.
- `live-server`, `live-run-body` and `live-empty` passed on the CLI 2.1.283.
- Not seen live: a real Claude Code cancel reaching the new log line. It needs a session with
  `telemetry.debug` on, cancelled mid-call.

Docs: `docs/design/architecture.md` says `telemetry.debug` lowers the logger to DEBUG and names the cancel line.
`telemetry.debug`'s description in `lib/config.py` is what the settings page shows.

Checked on Windows 10 on 2026-09-30.
