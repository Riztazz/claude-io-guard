---
title: Build the hook entry point, its answers and the MCP hook bridge
stage: A
area: runtime
created: 2026-09-27
status: open
depends-on: [06, 07]
findings: []
platforms: [windows, macos]
commit: "feat: one hook entry point that answers every event and fails open"
---

## Why

The pipeline decides, and the harness needs its answer in the documented JSON for each event. Two surfaces reach
the same entry point: a command hook reading stdin, and an `mcp_tool` hook whose fields arrive substituted into a
map of strings (D13). Both must give the same answer for the same event.

## What to build

`docs/design/architecture.md`, section 6, is the design.

- **`hooks/entry.py`:** `run_event(raw, surface, ctx)` builds the `Event`, runs the pipeline and returns the answer.
- **`hooks/answer.py`:** an `Outcome` into each event's JSON. For PreToolUse the verdict and the rewrite mode for
  the session's permission mode decide the shape: `deny` with the rendered reason, `ask` or `allow` with
  `updatedInput`, or context only (D12).
- **`hooks/bridge.py`:** the substituted map into `Event.from_fields`. Task 03 item 12 recorded that every value
  arrives as a string and an absent one as an empty string, so `tool_input` and `tool_response` travel whole as
  the JSON text of `${tool_input}` and `${tool_response}`, and the bridge decodes them
  (`docs/design/architecture.md`, sections 2 and 6). Check live that `${tool_response}` substitutes like
  `${tool_input}`, and that a 125 KB Write arrives whole, since task 03 probed neither.
- **`scripts/hook.py`:** reads stdin as bytes, decodes UTF-8, writes one ASCII JSON answer to stdout and exits 0.
  A crash before the answer prints `{}` and logs `GUARD_ERROR`. It replaces task 06's no-op hook.
- The `hook.*` MCP tools that call the bridge arrive with the server, in task 23.

## Where

`plugins/io-guard/scripts/ioguard/hooks/`, `plugins/io-guard/scripts/hook.py`, `tests/hooks/`.

## Done when

- The hook-level tests pass in CI on both platforms: JSON in, the documented JSON out, with `hook.py` run as a
  subprocess for every event and every rewrite mode.
- The bridge tests pass on the field maps task 03 recorded.
- Live on Windows, the empty pipeline answers every guarded tool call, and a deliberately broken check leaves the
  session working (D7).
