---
title: Bind each asked approval to the one call it was asked for, and let it expire
stage: H
area: mcp
created: 2026-09-29
status: done
depends-on: []
findings: [security-review-2026-09-29-4]
platforms: [windows, macos]
commit: "fix: an approval counts only for the call that asked it"
---

## Why

Fable's security review of 2026-09-29, finding 4, medium to high, checked in the code the same day.
`checks/trust_ask.py`, `run_rules.py` and `restore_ask.py` add to `SessionState.asked_trust`, `asked_runs` and
`asked_restores` when the hook answers ask, before the user answers, keyed by the call's content and never
expired. `io.trust`, `io.run` and `io.restore` then accept any later call with the same content. A prompt the
user declined leaves its entry, and a later identical call whose hook did not run, for a timeout or a failure,
finds it and proceeds with no prompt shown. The harness timing is not reproduced.

## What to build

- Key each entry by the hook event's `tool_use_id` as well as its content, and have the tool compare it with
  `call.tool_use_id`, which `mcp/protocol.py` already reads from `_meta` `claudecode/toolUseId`. context.md,
  "Hooks and MCP" row 38, confirms Claude Code sends it on a plugin server's `tools/call`, the same id the call's
  hooks receive, on 2.1.281 and 2.1.283. A call that arrives without one is refused, since it cannot be bound.
- Give each entry a short time to live, such as two minutes, and drop it when used.
- Tests: a declined ask followed by a hookless identical call is refused, for all three tools.

## Done when

- An entry from one call never lets another call through, and the three live probes still pass.

## What changed

- `lib/context.py`: `SessionState.asked` replaces `asked_runs`, `asked_restores` and `asked_trust`. It maps a
  call's tool use id to the content key its hook put to the user and the time. `keep_ask` records nothing for a
  call with no id, and drops entries past `ASK_LIFETIME`. `take_ask` spends the entry for that id, and is true
  only for the same content within the lifetime.
- `checks/trust_ask.py`, `run_rules.py` and `restore_ask.py` record through `keep_ask` with the event's
  `tool_use_id`. `mcp/tools_trust.py`, `tools_run.py` and `tools_history.py` check through `take_ask` with
  `call.tool_use_id`, and their refusals say no prompt on this call asked.
- The lifetime is ten minutes, not the two the task suggested. The id already keeps an entry from reaching any
  other call, so the lifetime only clears entries no call takes. Two minutes would refuse a user who reads the
  prompt for longer.
- `tools/probes/run_probe.py`: `live-run-asked` now also fails when `io.run` refused the approved call.
- Docs: `docs/design/architecture.md` (SessionState), `docs/live-checks.md` (a row), `docs/compat.md`, and
  `context.md` row 38. The README, the drawing and the skill tables needed nothing (`tools/skill.py --check`
  exits 0).

Evidence:

- `python tests/run_all.py`: 922 tests, OK, up from 915. The new ones: four in `tests/lib/test_context.py`
  (one yes lets one call through, another id, no id or other content does not, an expired entry does not and
  goes, a call with no id is never kept), and one per tool where the hook asked under one id and the same call
  arrives with another id or none: `io.run` refuses with `RULE_ASKED`, `io.restore` writes nothing, `io.trust`
  approves nothing.
- Live, Claude Code 2.1.283 on Windows: `live-run-asked`, `live-restore` and `live-trust` pass
  (20260929-121759, -121811, -121827). Each tool acted on the yes only through its own hook's entry, so the
  hook's `tool_use_id` equals the `tools/call`'s `claudecode/toolUseId` for all three.

Checked on Windows 10 on 2026-09-29. Not checked: macOS live (task 36), and a declined prompt live, since the
probes' permission tool always answers yes. The unit tests cover the declined case.
