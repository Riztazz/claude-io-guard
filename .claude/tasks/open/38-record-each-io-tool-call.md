---
title: Record each io tool call in telemetry
stage: F
area: mcp
created: 2026-09-28
status: open
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
