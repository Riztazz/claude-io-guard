---
title: Build the io MCP server, its hook bridge and its safety net
stage: F
area: mcp
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-27
depends-on: [03, 06, 08, 15]
findings: [BYT-4, INP-4]
platforms: [windows, macos]
commit: "feat: the io MCP server, dual-era, serving the hooks and the io tools"
---

## Why

Some primitives cannot be a hook around a built-in tool: a batch edit, a splice, an append, a run with an argument
list. They need tools of their own. MCP writes are invisible to rewind and read tracking (D3), so the server stays
small and every result says so.

The same server runs the hook checks (D13): one process per session, shared by the session's subagents, so no Python
starts per call and the caches are shared. Claude Code restarts a server that exited on the next hook call. A server
that cannot start leaves every hook failing open, and the model hears nothing (`context.md`, "Hooks and MCP", row
18), so the server must not die silently.

## What to build

`docs/design/architecture.md`, sections 7 and 8, is the design.

- **Transport and eras.** A stdio JSON-RPC server on the standard library alone. The legacy era comes first,
  because Claude Code connects stdio servers with `initialize` (D9): `initialize` and `notifications/initialized`
  select 2025-11-25 semantics for the process. The modern era follows: `server/discover`, `_meta` validation with
  `-32602` and `-32022`, and `resultType` on every result. Claude Code's modern client rejects a result without
  `resultType`, `resources/list` included, and a `tools/list` without a number `ttlMs` and a `cacheScope` of
  `public` or `private` (row 15).
- **Tools.** `ToolSpec`, the generated schemas and `tools/list` in a fixed order. Every output schema sets
  `additionalProperties: true`, because the client validates `structuredContent` against it. Annotations come from
  `read_only`, `destructive` and `idempotent`. An expected failure is a result with `isError: true` and the fix.
  Every fix names the callable name, such as `mcp__plugin_io-guard_io__io_edit`, and the ToolSearch step. When a
  result has `structuredContent`, the model reads that JSON and not the text copy (row 16), so the structured
  result carries the message and the fix, and stays compact.
- **The hook bridge tools:** `hook.pre_tool_use`, `hook.post_tool_use`, `hook.post_tool_use_failure` and
  `hook.ping`, registered last with the description "Called by Claude Code hooks. Not for the model." They call
  `hooks.bridge.call` from task 08, and they never set `isError`. `hooks.json` already binds PreToolUse,
  PostToolUse and PostToolUseFailure to the first three, and task 08's stub `server.py` serves them. The new
  server keeps the stub's tool names and `bridge.DESCRIPTION`, and adds `hook.ping`.
- **One set of once-per-session keys across processes.** The SessionStart command hook and the server each keep
  their own `SessionState`, so task 08's `live-broken` run showed a broken check's warning twice. Keep the warned
  keys in the plugin data folder, per session, so a warning goes out once whichever process gives it.
- **The concurrency model:** a reader thread, a writer lock, four workers, a telemetry queue, a pump per background
  run and a watchdog. `paths.LockTable` serialises one file inside the process, and `lib.locks.file_lock` serialises
  it across two sessions' servers.
- **The safety net:** a fail-open dispatcher around every message, a reader that survives a malformed line, a
  heartbeat file the watchdog writes every 5 seconds, and a `UserPromptSubmit` command hook that warns once when the
  heartbeat is older than 30 seconds (`SERVER_DOWN`).
- **The launch:** `.mcp.json` from task 06, with `${user_config.python}`.
- **Handles, progress and cancellation** as section 7 says. **No tool relies on elicitation to reach the user.**
  The desktop declines a legacy `elicitation/create` without showing it, `claude -p` cancels it, and in the modern
  era a server-sent `elicitation/create` is never answered, which hangs the call. A modern tool that must elicit
  answers `input_required`, which the client does resume (row 16). Asking the user goes through a hook `ask`
  instead, as task 25 does.
- **Bounded results.** A result stays under 25,000 tokens. Longer output goes to a file under the scratchpad, and
  the result names it.
- **`io.read`.** A byte-exact read with the profile header and line ranges. Text or binary is decided by sniffing
  the bytes (INP-4).

## Where

`plugins/io-guard/.mcp.json`, `plugins/io-guard/hooks/hooks.json`, `plugins/io-guard/scripts/server.py`,
`plugins/io-guard/scripts/ioguard/mcp/`, `tests/mcp/`.

## Done when

- The conformance tests drive the server in both eras from recorded requests, in CI on both platforms.
- Live on Windows, `/mcp` lists the server, and the era it used is recorded, with and without
  `MCP_PROTOCOL_NEGOTIATION=auto`.
- Live on Windows, the hook checks answer through the bridge tools. Three parallel subagents editing one file
  through `io.edit` serialising without a lost edit moved to task 24, which builds `io.edit`.
- A server that cannot start again after it dies gives the heartbeat warning on the next turn, and the tool calls
  still run.
- `io.read` returns a CRLF fixture with a BOM, with the right profile, and the server starts in under 500 ms.

## What changed

Checked on Windows 10 on 2026-09-28, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **`mcp/` replaces the stub server.** `protocol.py` answers both eras: `initialize` makes the process legacy, a
  request with a protocol version in `_meta` makes it modern, `server/discover` answers in either, a modern
  result carries `resultType` and the server's info, and a modern request missing its `_meta` fields gets
  `-32602`, or `-32022` for an unknown version. `toolspec.py` makes each tool's schemas from its dataclasses,
  loose for output, and its registry parses arguments, answers a tool's bug as `GUARD_ERROR` and a hook tool's
  bug as `{}`, and saves a result past 80,000 characters to a file it names. `server.py` runs the reader, four
  workers, one writer lock and the watchdog, and points `sys.stdout` at stderr. `tools_hook.py` keeps the three
  hook tools and adds `hook.ping`. `tools_read.py` is `io.read`.
- **The safety net.** The watchdog rewrites `sessions/<session>.alive` every 5 seconds, named by
  `CLAUDE_CODE_SESSION_ID`, and marks it stopped at the end. The new `server.heartbeat` check runs in a new
  `UserPromptSubmit` command hook and warns once, as `SERVER_DOWN`, when the beat is 30 seconds old with no stop.
  A cancelled call answers `CANCELLED`.
- **Found live, row 33: a plugin server that fails to start is skipped for 15 minutes in every session,** through
  Claude Code's own `~/.claude/mcp-needs-auth-cache.json`, with every hook failing open and nothing said. So with
  no heartbeat for its session, `server.heartbeat` reads that cache and names the skip and when it ends. The
  `live-server-down` probe removes the entry its dead server leaves, or every probe after it fails for 15 minutes.
- **One set of warned keys across the session's processes:** `SessionState.shared` keeps them in
  `sessions/<session>.warned`, under the new `lib.locks.file_lock`, so the server and each command hook warn once
  between them. `hooks.entry.LiveContexts.get` takes the session and folder, and `bridge.context` hands the io
  tools the same context.
- **Choices made here, reported to the lead on 2026-09-28 before building:** telemetry takes one lock per append
  instead of a queue thread, so a crash loses no line. `paths.LockTable` and the three-subagent Done-when moved to
  task 24, with `io.edit`. `HandleStore`, `HANDLE_EXPIRED` and `ProgressReporter` moved to task 25, with `io.run`.
  No elicitor is built, because no tool needs one and no surface shows its form. A project's `error_patterns`
  from task 22 carries the regex risk task 25's note describes, and that note now names it.
- **`test_meta` read two test files with one name as one,** so `tests/lib/test_heartbeat.py` hid
  `tests/checks/test_heartbeat.py`. It keys them by path now.

Evidence:
- `python tests/run_all.py` ran 585 tests, all passing, against 560 after the CI fix. The stub server's 6 tests
  became the new server's, run from `tests/mcp/requests/legacy.jsonl` and `modern.jsonl` against the shapes
  recorded beside them.
- `run_probe.py verdicts`: `live-server`, `live-server-modern` and `live-server-down` pass on 2.1.281 and
  2.1.283. The server connected in 191 to 250 ms, `/mcp`'s list in the stream showed it `connected`, and its
  heartbeat recorded `legacy`, or `modern` under `MCP_PROTOCOL_NEGOTIATION=auto`. The model read `io.read` of
  `keep.txt` as `"profile": "CRLF, BOM, UTF-8, 2 lines"` with the BOM and each CR in its text. After a test check
  killed the server and its restart failed, the next turn's hook answered `SERVER_DOWN` and that turn's Bash ran.
  `live-empty`, `live-broken`, `live-answers` and `live-diagnose` still pass on 2.1.283 through the new server.
- The server answers `initialize` 141 to 158 ms after its process starts, p50 145 ms over 20 starts, under the
  500 ms the Done-when sets.

Docs updated: `architecture.md` sections 1 to 8. `context.md`: rows 33 and 34 and a task 23 paragraph.
`live-checks.md` and `compat.md`. The README's status line, the io tools table and what happens when the server
stops. `launcher.md`. `CLAUDE.md`'s layout. The drawing's heartbeat step, which now names a server Claude Code
skipped.

Not checked:
- macOS, live or in CI until the lead pushes. Task 36 holds the macOS live checks of the server and the lock.
- The heartbeat hook costs 237 to 293 ms a turn: Git Bash starting `hook.sh` about 90 ms, and Python's imports
  about 120 ms. Nothing here trims it.
- `CLAUDE_CODE_SESSION_ID` in the server's environment was read on 2.1.283 only. The 2.1.281 runs rely on it,
  since their heartbeats named their sessions, but no probe printed the variable there.
