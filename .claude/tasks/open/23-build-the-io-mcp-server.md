---
title: Build the io MCP server, its hook bridge and its safety net
stage: F
area: mcp
created: 2026-09-27
status: open
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
- Live on Windows, the hook checks answer through the bridge tools, and three parallel subagents editing one file
  through `io.edit` serialise without a lost edit.
- A server that cannot start again after it dies gives the heartbeat warning on the next turn, and the tool calls
  still run.
- `io.read` returns a CRLF fixture with a BOM, with the right profile, and the server starts in under 500 ms.
