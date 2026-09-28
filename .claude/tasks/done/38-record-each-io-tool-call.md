---
title: Record each io tool call in telemetry
stage: F
area: mcp
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [23, 24]
findings: []
platforms: [windows, macos]
commit: "feat: one telemetry line per io tool call"
---

## Why

`docs/design/architecture.md`, section 9, records "one JSONL line per decision or tool call", and the drawing's
io tool flow says "Each call is one telemetry line". No io tool writes one: `io.read` since task 23, and
`io.edit`, `io.splice` and `io.append` since task 24. Task 28's report and task 31's measurement count what the
io tools did, so this lands before task 28, although its number comes after it. Task 24 found the gap and filed
it here rather than widen its own change.

## What to build

- **`ToolRegistry.call` records one `TelemetryEvent` per io tool call**, surface `mcp_tool`: the tool's name,
  the code of a refusal or `GUARD_ERROR`, the latency, the file's extension and the bytes written. No content,
  as section 9 says. A hook tool records nothing here, because the pipeline already records each hook call.
- **`ToolCall` carries the session's id**, from `CLAUDE_CODE_SESSION_ID`, which `TelemetryEvent` needs.
- **A cancelled call records `CANCELLED`.**

## Where

`plugins/io-guard/scripts/ioguard/mcp/toolspec.py`, `mcp/server.py`, `tests/mcp/test_toolspec.py`.

## Done when

- A test calls an io tool through the registry and reads one telemetry line with the documented fields, and
  one with the code of a refused call.
- A `live-*` probe's copied telemetry holds a line for its io tool calls.

## What changed

- **`ToolRegistry.call` records one `TelemetryEvent` per io tool call** through `toolspec.recorded`:
  `surface` `mcp_tool`, `event` `tools/call`, the tool's name, the code and severity of a refusal, `CANCELLED`
  or `GUARD_ERROR`, null for a call that answered, `latency_ms`, the extension of the call's `path` or first
  of its `paths`, and `bytes`. A `GUARD_ERROR` line carries the exception type and a hash of the traceback. A
  hook tool records nothing here. A line that cannot be written is logged, and the call answers as it would
  have.
- **`ToolCall` carries `session`**, from `CLAUDE_CODE_SESSION_ID` or `io-server` without one, and
  **`traceparent`**, which `Protocol.call` takes from the request's `_meta`.
- **`bytes`** comes from a `written_bytes()` method on the outputs that write a user's file: `ChangeOutput`
  and `FormatOutput`, whose results now carry each file's size after the call as `bytes`. A call that changed
  nothing wrote 0.
- Tests: 685 before, 690 after, all passing, from `python tests/run_all.py`. `tests/mcp/test_toolspec.py`
  reads the line of an `io.edit` through the real registry, with its fields and no text of the file, a
  refused call's `ANCHOR_NOT_FOUND`, a cancelled call's `CANCELLED`, a bug's `GUARD_ERROR` with its type, no
  line for a hook tool, and a failing telemetry that leaves the answer as it was. The helper `ToolCall` in
  that file now carries a `Context.fake`.
- **Evidence.** `live-format` on the CLI 2.1.283 and the desktop's 2.1.281: the session's telemetry held a
  `tools/call` line for `io.edit`, 5.0 and 6.9 ms and 68 bytes, and one for `io.format`, 70.6 and 68.1 ms and
  88 bytes. Its verdict now requires both lines.
- **Docs:** `docs/design/architecture.md` sections 7 and 9, `docs/live-checks.md` and `context.md`. The
  drawing already says each io tool call is one telemetry line.
- Checked on Windows on 2026-09-28. macOS waits in task 36.
