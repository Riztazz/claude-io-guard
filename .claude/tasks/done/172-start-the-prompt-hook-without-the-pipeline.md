---
title: Answer the prompt hook for a running server before the pipeline loads
stage: I
area: hooks
created: 2026-10-01
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "perf: start the prompt hook without the whole pipeline"
---

## Why

The performance pass of 2026-10-01. The `UserPromptSubmit` command hook starts a new Python on every prompt,
through `sh pyrun hook.py heartbeat`, and Claude Code waits for it before the turn starts. It took 222 ms at
p50 over 15 starts, 163 ms of it imports: `hook.py` loaded the whole check pipeline, 227 modules, to run one
check that reads one small file. Telemetry shows only the 4.9 ms spent inside that Python.

## What changed

- `hooks/beat.py`, new: `running(raw, env)` reads the session's `sessions/<session>.alive`. A beat younger
  than `FRESH_S`, 10 seconds, or a clean stop leaves `server.heartbeat` nothing to say. Any other state, a
  missing, torn or old file among them, goes to the pipeline as before.
- `hook.py`: the `heartbeat` event asks `running` first and answers `{}` when it says so. `traceback` loads
  only when a hook fails.
- `lib/heartbeat.py`: `FRESH_S` and `quiet(data, now, stale_s)`, which the check now calls too, so the fast
  answer and the check agree. A `stale_s` under 10 counts as 10, since the server beats every 5 seconds. The
  setting's description says so.
- `lib/folders.py` imports nothing of io-guard's. `repository_root` moved to `lib/ports.py`, beside
  `read_or_none`, and its three callers import it from there. `SESSION_ID` moved from `lib/events.py` to
  `lib/folders.py`, beside `session_file`, which turns the id into a path, so `hooks.beat` checks the id by
  the same pattern.
- Tests: `TheHeartbeatHookAnswersARunningServerAtOnce` in `tests/hooks/test_hook_py.py` runs `hook.py` as a
  subprocess. A fresh beat answers `{}` and `-X importtime` shows no `ioguard.checks.pipeline`. That test
  failed first. A beat two minutes old still gives `SERVER_DOWN`. `AHeartbeatLeavesNothingToSay` in
  `tests/lib/test_heartbeat.py` covers the edges and the floor of 10 seconds.
- Telemetry: a prompt with a running server no longer writes a `UserPromptSubmit` line, so `report.py` counts
  fewer of them. Nothing reads those lines but the count.
- Docs: `docs/design/architecture.md` (the package tree, the hook's cost, `folders` and `ports`),
  `docs/launcher.md` (the per-turn hook's cost). The drawing's steps still hold.

Evidence:

- `sh pyrun hook.py heartbeat`, 15 starts each, a fresh beat in a test folder: HEAD's tree 364 ms at p50, this
  change 120 ms. A stale beat in this change, which runs the whole pipeline and warns: 270 ms.
- `python tests/run_all.py`: 1,174 tests, OK, 2 skipped, against 1,171. `python tools/skill.py --check`
  exits 0.

Checked on Windows 10 on 2026-10-01.
