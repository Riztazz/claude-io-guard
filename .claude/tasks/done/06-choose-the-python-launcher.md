---
title: Start the server and the two command hooks the same way on both platforms
stage: A
area: runtime
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [03]
findings: [SHL-3]
platforms: [windows, macos]
commit: "feat: start the guard's Python the same way on Windows and macOS"
---

## Why

No interpreter name works on both platforms. On Windows `python.exe` is the real interpreter and `python3` is the
Microsoft Store stub on the lead's machine. On macOS `python3` exists and `python` may not. Claude Code installs
no Python packages for a plugin, so nothing can be installed for us. With the one-process runtime (D13) only two
things start Python: the io server, and the command hooks for SessionStart and the per-turn heartbeat.

## What to build

`docs/design/architecture.md`, section 6, "The launcher across Windows and macOS", is the design.

- **The server** starts from `plugins/io-guard/.mcp.json` with `"command": "${user_config.python}"`, which defaults
  to `python3` (D15), and `PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8` and `IOGUARD_DATA` in its `env`.
- **`scripts/hook.sh`**, POSIX sh, runs under Git Bash on Windows and `sh` on macOS. It finds an interpreter with
  `command -v` in the order `python3`, `python`, `py -3`, skips any path under `WindowsApps`, and runs `hook.py`
  with the event name. With no interpreter it prints a `systemMessage` naming the fix and exits 0.
- **The fallback**, for a harness where task 03 item 12 fails: every tool event as a shell-form command hook through
  `hook.sh`. The README carries it as a settings snippet.
- **The first real hook:** a no-op PreToolUse on `Bash|PowerShell|Edit|Write|Read` that writes one JSONL line per
  call to `${CLAUDE_PLUGIN_DATA}`. It proves the wiring, and task 08 replaces it.
- **Measure** 100 no-op calls through each path: the `mcp_tool` hook on task 03's probe server, the command hook
  through `hook.sh`, and the exec form. Record p50 and p95 in `docs/launcher.md`. Task 03's ten-call run gives
  the expected order (`context.md`, "Hooks and MCP", rows 9 and 12): `mcp_tool` 1.4 and 3.9 ms, exec 58.3 and
  74.7 ms, shell through Git Bash 89.7 and 97.0 ms. `tools/probes/run_probe.py` times hooks from the stream
  lines, and the measurement reuses it.
- **`mcp_tool` is the primary path.** Task 03 item 12 confirmed it, so the fallback above stays a documented
  snippet, never the default.

## Where

`plugins/io-guard/.mcp.json`, `plugins/io-guard/hooks/hooks.json`, `plugins/io-guard/scripts/hook.sh`,
`plugins/io-guard/scripts/hook.py`, `docs/launcher.md`.

## Done when

- One `hooks.json` and one `.mcp.json` start the no-op hook and a stub server on Windows, with the lead's
  `userConfig.python` set to `python`.
- The chosen path's p95 fits the 300 ms budget (D16), and `docs/launcher.md` holds the numbers for all three.
- A missing or wrong interpreter gives one clear warning per session and never blocks the tool call (D7).
- `hook.sh` passes `sh -n` in CI on the macOS runner. Its live start on the Mac waits in task 36.

## What changed

- **`plugins/io-guard/.mcp.json`:** the server `io`, started from `${user_config.python}` with
  `scripts/server.py`, and `PYTHONUTF8`, `PYTHONIOENCODING` and `IOGUARD_DATA` in its `env`.
- **`plugins/io-guard/scripts/server.py`:** a stub server in the legacy era. Its one tool, `hook.pre_tool_use`,
  writes a line per call to `events/<YYYY-MM>/<session>.jsonl` in the plugin data folder and returns no
  decision. It fails open: a crash in a call answers with no decision. Task 23 replaces it.
- **`plugins/io-guard/hooks/hooks.json`:** the no-op PreToolUse hook on `Bash|PowerShell|Edit|Write|Read`, as an
  `mcp_tool` hook with the input map of `architecture.md`, section 6, and SessionStart as a shell-form command
  hook, `sh "${CLAUDE_PLUGIN_ROOT}/scripts/hook.sh" session_start`. Starting it through `sh` needs no
  executable bit.
- **`plugins/io-guard/scripts/hook.sh`:** POSIX sh on builtins only. It tries `$CLAUDE_PLUGIN_OPTION_PYTHON`,
  the user's setting, first, then `python3`, `python` and `py -3`. It skips anything under `WindowsApps` and
  answers a `systemMessage` when it finds nothing. It strips its own folder from `$0` at either separator,
  because a Windows caller may pass backslashes only.
- **`plugins/io-guard/scripts/hook.py`:** the command-hook entry point. It records each event, and on
  `session_start` it checks that its own Python and the server's interpreter are 3.14 or later, warning once
  otherwise. It avoids syntax newer than 3.8 so an old Python gets far enough to say so.
- **No command-hook fallback ships.** The task planned one for a harness where `mcp_tool` hooks fail. Task 03
  and task 04 found them working on every supported release, and the planned snippet could not work anyway:
  user settings cannot name `${CLAUDE_PLUGIN_ROOT}`, and `/hooks` is read-only. `architecture.md` and
  `docs/launcher.md` say so.
- **Tests, 36 in all, up from 19:** `tests/hooks/test_launcher.py` runs `hook.sh` under a controlled PATH and
  `hook.py` as a subprocess. It covers no Python, the Store stub skipped, a control proving the fake stub would
  run outside `WindowsApps`, a working Python, and a wrong setting. `tests/mcp/test_server_stub.py` drives the
  stub server over pipes. `tests/test_plugin_files.py` checks that the marketplace, the manifest, the hooks and
  `.mcp.json` agree.
- **`.github/workflows/ci.yml`** gained `sh -n` on `hook.sh`. **`tools/probes/run_probe.py`** gained the
  `hooksh` hook form and the three 100-call launch probes, and `run all` now runs only the probes with a
  verdict.
- **`.claude/launch.json`:** a `docs` entry that serves `docs/` on 127.0.0.1:8765, for the drawing check that
  `.claude/rules/docs.md` asks for.
- **Docs:** `docs/launcher.md` is new. `docs/design/architecture.md`, section 6, describes the launcher as built
  and drops the fallback, and section 8 no longer says Claude Code never reconnects a stdio server, which task 03
  disproved and task 03 missed there. `docs/architecture.svg`: the `hook.sh` box's hover text no longer names the
  fallback. It parses as XML, is ASCII, and flow C plays in the browser pane with no console error.
  `README.md`: the install step says what a wrong interpreter does. `docs/compat.md`, `docs/live-checks.md`,
  `context.md` and `CLAUDE.md` carry the new facts and files.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- **Installed from the local marketplace with `python` set to `python`**, one headless session each on the CLI
  2.1.283 and the desktop app's `claude.exe` 2.1.281: the server connected in 67 to 69 ms, and the plugin data
  folder got `session_start` from `hook.sh`, then `PreToolUse` for Bash and for Read from the `mcp_tool` hook.
- **Set to `io-guard-no-such-python`:** one `systemMessage` at SessionStart, quoting the setting and naming
  `/plugin configure io-guard`. Both tool calls ran. The harness added `MCP server 'plugin:io-guard:io' not
  connected` to each hooked call, which io-guard cannot suppress.
- **Not set at all:** the server ran the default `python3`, the Store stub, so an unset option does fall back
  to its default. `hook.sh` skipped the stub, ran `python`, and gave the same one warning.
- **100 Bash calls per path**, CLI 2.1.283: `mcp_tool` p50 1.2 ms and p95 1.6 ms, exec form 53.4 and 58.0 ms,
  through `hook.sh` 129.8 and 139.1 ms. The chosen path's p95 fits the 300 ms budget with room to spare.
- `sh -n plugins/io-guard/scripts/hook.sh` passes under Git Bash.
- io-guard was removed afterwards with `claude plugin marketplace remove claude-io-guard`.
  `~/.claude/settings.json` keeps the empty `enabledPlugins`, `extraKnownMarketplaces` and `pluginConfigs`
  objects the CLI leaves behind.

Not checked:

- **Live starts on macOS.** CI run 36317022051 on `f968f32` passed `sh -n` on `hook.sh`, and the whole suite,
  the launcher tests included, on both macOS jobs. A live session on a Mac waits in task 36 (D21).
- **The desktop app's own window with io-guard loaded.** Its bundled binary ran the check headless, and task
  02 already showed the Code tab loading the plugin.
- **Windows with no Git Bash.** Shell-form hooks run through PowerShell there, and `hook.sh` cannot start.
