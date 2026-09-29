---
title: Keep a hook call's session id and paths inside io-guard's folder and the session
stage: I
area: hooks
created: 2026-09-29
status: done
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
harness's `_meta`. A forged event also changes nothing about the checks on Claude Code's own calls. What it
reaches is io-guard's own reads and writes: a forged PreToolUse of a long heredoc makes `transport.body`
write a body the model chose into `<scratchpad_dir>/io-guard/`, anywhere, which is a write that no Write
permission sees. The only reader of `transcript_path` is `diagnose.refused` (`checks/diagnose.py`, the
`read_tail` of `tail_bytes`), which quotes lines of a refused call back into the answer.

The probe logs answer the question below already. Across every recorded probe run of 2026-09-27 and
2026-09-28, each hook's `tools/call` came with no `_meta` at all (`dead-server`, `guard-fields`,
`launch-mcp`, 100 calls a run, and the rest), and each model's call carried `_meta`
`claudecode/toolUseId` (`ask-prompt`, `era-legacy`, `era-auto`, `features-modern`).

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

## What changed

- `mcp/tools_hook.py`: a hook tool called with a tool use id in `_meta` is the model's, and answers an error,
  `isError` set, with no check run and no telemetry line. That closes the forged event at the door, so what
  follows is the second line.
- `lib/events.py`: a `session_id` of anything but letters, digits, `-` and `_` is an `EventError`, and the hook
  answers nothing.
- `checks/transport_body.py`: `body_folder` writes into `scratchpad_dir` only when it is absolute, by the
  platform's own path rules, and not inside the project. Otherwise a body goes to io-guard's `bodies/`. The
  task asked for a folder that exists too. That was left out: Claude Code creates the scratchpad lazily, and
  the door above already stops a forged path.
- `checks/diagnose.py`: `diagnose.refused` reads `transcript_path` only under Claude Code's `projects`
  folder, `CLAUDE_CONFIG_DIR` or `~/.claude`, with a debug line otherwise.
- Tests, each failing first: six ids refused and three kept in `tests/lib/test_events.py`, the model's call
  in `tests/mcp/test_server.py` against the real server, a scratchpad inside the project and a relative one
  in `tests/checks/test_transport_body.py`, and a transcript outside the projects folder in
  `tests/checks/test_diagnose.py`. `tests/support/events.py` puts the test transcript where Claude Code keeps
  one. The suite is 977, all passing, on Windows.
- The probe logs answered the question, and `context.md` records it as "Hooks and MCP", row 42. With the
  refusal in place, `live-empty`, `live-answers` and `live-diagnose` passed on the CLI 2.1.283, so the hooks'
  own calls still run every check and a real transcript is still read.
- Docs: `docs/design/architecture.md` (the event's session id, the hook tools, the transcript read),
  `docs/live-checks.md` and `docs/compat.md` (the new fact, with `live-empty` as its watch after a release),
  `context.md`.
- Checked on Windows on 2026-09-29. Not checked: the desktop's 2.1.281 live, though its probe logs show the
  same, and macOS, which waits in task 36.
