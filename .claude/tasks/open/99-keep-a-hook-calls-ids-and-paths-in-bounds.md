---
title: Keep a hook call's session id and paths inside io-guard's folder and the session
stage: I
area: hooks
created: 2026-09-29
status: open
depends-on: [98]
findings: []
platforms: [windows, macos]
commit: "fix: a hook call's session id and paths stay inside io-guard's folder"
---

## Why

The code review of 2026-09-29: slice C item 5, slice B item 4, and slice A item 1's second route. The hook
tools, `hook.pre_tool_use` and the rest, are in `tools/list`, so the model can call them with an event it
wrote. Nothing checks the event's fields:

- `session_id` becomes a file name in `events/<month>/<id>.jsonl`, `sessions/<id>.warned` and
  `sessions/<id>.dirty`. `../../../ESCAPED` wrote `ESCAPED.jsonl` outside io-guard's folder, with a telemetry
  line in it. Rerun on Windows on 2026-09-29.
- `transcript_path` is read by `diagnose.refused`, `scratchpad_dir` names where `transport.body` writes a body
  file, and `persistedOutputPath` names a file to read (task 98).

A forged event cannot record an ask a real call spends, because the real call's tool use id comes from the
harness's `_meta`.

## What to build

- `lib/events.py`: a session id is letters, digits, `-` and `_` only. An event with any other id is refused as
  malformed, with a debug log line, and the hook answers nothing.
- `transcript_path` is read only under `<config dir>/projects/`. `scratchpad_dir` is used only when it is an
  absolute folder that exists, and outside the project. Otherwise the body goes to io-guard's `bodies/`.
- Find out whether the server can tell a hook's call from the model's. A model's `tools/call` carries
  `_meta` `claudecode/toolUseId` (context.md, "Hooks and MCP", row 38). If a hook's call carries none, or
  carries something only a hook's does, the hook tools refuse the model's calls. Check it live with a probe
  first, and record the answer in `docs/live-checks.md`.

## Where

`lib/events.py`, `lib/context.py` (`session_file`), `lib/telemetry.py` (`path_for`),
`checks/diagnose.py`, `checks/transport_body.py`, `mcp/tools_hook.py`.

## Done when

- The `../../../ESCAPED` event writes nothing outside io-guard's folder, and a forged `transcript_path` or
  `scratchpad_dir` is not read or written.
- The live probe's answer is recorded.
