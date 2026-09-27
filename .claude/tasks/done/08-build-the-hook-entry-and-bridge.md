---
title: Build the hook entry point, its answers and the MCP hook bridge
stage: A
area: runtime
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
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

## What changed

- **`plugins/io-guard/scripts/ioguard/hooks/`:**
  - `entry.py`: `run_event(raw, surface, ctx=None, registry=None)` reads the event, runs the pipeline and
    answers, and never raises. `LiveContexts` loads the config and the probe once per session and project and
    keeps one `SessionState` per session. The config's one message goes out with the session's first answer.
  - `answer.py`: an `Outcome` into each event's JSON, as the table in `architecture.md`, section 6, says. A
    refusal outranks an ask, which outranks an allow. A line for the model alone never carries a
    `permissionDecision`, so no prompt is skipped.
  - `bridge.py`: `call(fields)` runs the substituted map through `run_event` and returns the answer as the
    tool's text, never with `isError`.
- **`scripts/hook.py`** runs every event through `run_event` and always writes one JSON object. Its own
  recording is gone, because the pipeline's telemetry replaces it. **`scripts/server.py`**, still the stub until
  task 23, serves the three hook tools through the bridge. **`hooks/hooks.json`** binds PostToolUse and
  PostToolUseFailure too, with `${tool_response}` and `${error}`.
- **Two changes in task 07's code.** `Context.live` takes no data folder, and then has no user layer, no probe
  and telemetry in memory. The pipeline's merge renders the results of a decision that does not refuse as
  context lines, so a check's warning reaches the model without the check repeating it. `lib.telemetry` gained
  `debug_log`, and the `ioguard` logger a `NullHandler`, so a traceback goes only to `debug.log`.
- **The layer rule was impossible as written.** `hooks.entry` runs the pipeline, which lives in `checks`, while
  the rule said the policy packages never import each other. Now `checks` imports `lib`, and `hooks`, `mcp` and
  `cli` import `lib` and `checks` and never each other, except `mcp.tools_hook` calling `hooks.bridge`.
  `tests/test_layout.py` enforces it.
- **Test checks that run in the shipped hook and server.** `tests/support/injected.py` holds five checks, one
  per answer shape, and `tests/support/inject/sitecustomize.py` installs the ones `IOGUARD_TEST_CHECKS` names in
  any Python started with that folder on `PYTHONPATH`. The subprocess tests and the live probes both use it.
- **`tools/probes/run_probe.py`:** a `guard` hook form that sends io-guard's own `hooks.json` maps, the
  `guard-fields` and `guard-large` probes, and four `live-*` probes that run io-guard from this checkout. A
  verdict about context reads the transcript's `hook_additional_context` attachments, because the model's
  summary leaves lines out.
- **Tests, 201 in all, up from 159:** `tests/hooks/test_answer.py`, `test_entry.py`, `test_bridge.py` and
  `test_hook_py.py`, the last starting `hook.py` on the recorded events for every event and every rewrite mode.
  `tests/fixtures/fields/` holds 13 field maps: ten recorded live from io-guard's own maps, and three of task
  03's `${tool_input}` texts in the same map.
- **Also carried here:** task 07's close edits, which missed `f8281bf`, at the lead's request.
- **Docs:** `docs/design/architecture.md` sections 1, 3 and 6, `context.md` (rows 19, 21 and 22 and the hook
  entry table), `docs/compat.md`, `docs/live-checks.md`, `README.md` (the status line), `CLAUDE.md`, the
  `io-guard-dev` skill, and tasks 17 and 23. The drawing already shows the bridge and `hooks.entry` as built.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- `python tests/run_all.py` ran 201 tests, all passing.
- **Live, CLI 2.1.283 and the desktop's 2.1.281, Haiku 4.5**, every verdict passing on both:
  - `live-empty`: Bash, PowerShell, Write, Read, Edit and a missing Read ran, with 13 hook answers, all
    `success`, and one telemetry line per hook call.
  - `live-broken`: a check raising on every event left all six calls running, and `w.txt` ended as `ONE`.
  - `live-answers`: the rewrite ran as `IOGUARD_REWRITTEN`, and the refusal's fix reached the model.
  - `live-refuse`: `dontAsk` denied with the command to run instead, and the model ran it.
  - `guard-fields`: `${tool_response}` arrives as the tool's output object in JSON text, and `${error}` as
    `Exit code 3`.
- **`guard-large`, CLI 2.1.283 only:** a Write of 145,599 bytes reached the hook as 148,340 characters of JSON
  text, and its `content` matched the file on disk byte for byte. The first run failed with "API Error:
  Claude's response exceeded the 32000 output token maximum.", so the probe now sets
  `CLAUDE_CODE_MAX_OUTPUT_TOKENS` to 64000.

Not checked:

- **The warning once per session across processes.** `live-broken` showed the broken check's warning twice,
  once from the SessionStart command hook and once from the server. Task 23 shares the keys.
- **Every path on macOS.** CI runs the tests there, and the live runs wait in task 36.
