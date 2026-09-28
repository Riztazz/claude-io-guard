---
title: Keep io-guard's state in one folder per user, whatever the plugin is called
stage: I
area: runtime
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [23, 28, 40]
findings: []
platforms: [windows, macos]
commit: "fix: keep io-guard's state in one folder whatever the plugin is called"
---

## Why

Claude Code gives each plugin a data folder named for its id, `~/.claude/plugins/data/<id>/`. The desktop app
loads io-guard as `io-guard@inline` when it comes from a local-folder marketplace or from claude.ai, and the
terminal loads it as `io-guard@synced` or `io-guard@<marketplace>`. One user then has two folders, each with its
own `config.json`, its own telemetry and, worst, its own lock table. A desktop session and a terminal session
editing one file would each take a lock the other never sees, which is the case D13 exists for. Fable's review
of 2026-09-28 found it, and the lead chose `~/.claude/io-guard/`.

## What to build

- `lib.context.home_folder(env)`: `IOGUARD_HOME`, then `io-guard` inside `CLAUDE_CONFIG_DIR`, then
  `~/.claude/io-guard`. The server, the command hooks, the pre-commit check and the report all use it, and
  nothing reads `${CLAUDE_PLUGIN_DATA}`.
- The probes keep their own folder through `IOGUARD_HOME`, and the test suite a temporary one.
- The README says where the folder is, what it holds, and that uninstalling leaves it.
- Move the lead's `config.json` and telemetry into the new folder, update the install, and check a desktop
  session after the lead restarts the app.

## Where

`plugins/io-guard/scripts/ioguard/lib/context.py` and its callers, `.mcp.json`, `tests/__init__.py`,
`tools/probes/run_probe.py`.

## Done when

- The live probes pass with their own folder on both releases.
- A desktop session after the reinstall starts the server, reads the lead's `config.json` from
  `~/.claude/io-guard`, and writes its telemetry there.

## What changed

- **The folder.** `home_folder` replaced `plugin_data`, which read `IOGUARD_DATA` or `CLAUDE_PLUGIN_DATA` and
  could return nothing. `.mcp.json` no longer passes `IOGUARD_DATA`. The server and `hooks.entry` lost their
  checks for a missing folder, and `cli.report.data_folders`, which globbed every `io-guard-*` data folder, is
  gone: `report` and `measure` read io-guard's folder unless `--data` names others, and say so when it doesn't
  exist. The pre-commit check now finds the user's `config.json` with no variable set.
- **Text a user reads.** `USER_FILE`, the fix a config refusal names, points at `~/.claude/io-guard`.
- **Tests.** `tests/__init__.py` points `IOGUARD_HOME` at a temporary folder under a test runner, so no test
  touches the user's folder. The injected test checks import that package too, in a hook or server with no
  runner loaded, and keep the folder they were started with. 743 tests before, 746 after, all passing on
  Windows: three for `home_folder`'s order and one that the suite uses a temporary folder, in place of the
  report's glob test, and the launcher's no-folder test now checks `CLAUDE_CONFIG_DIR`. The suite left no
  `~/.claude/io-guard` behind.
- **Live, 2026-09-28, Windows 10.** With `IOGUARD_HOME` at `workbench/io-guard-home`, `live-empty`,
  `live-server`, `live-server-down`, `live-answers` and `live-commit-policy` passed on the CLI 2.1.283 and the
  desktop's 2.1.281. `live-commit-policy` failed once on 2.1.283 when it ran beside `live-server-down`, whose
  failed restart made Claude Code skip io-guard's server for 15 minutes, and passed alone. `live-answers`
  failed once on 2.1.281 when Haiku called no tool at all, and passed on the rerun.
- **Docs.** `README.md` (the folder, its contents and uninstalling), `docs/design/architecture.md` (the new
  function, a paragraph on D30, the config table, section 8's shared state, the report), `docs/architecture.svg`
  (the `~/.claude/io-guard` box and its step), `CLAUDE.md`, the `io-guard-dev` skill, `context.md` (D30), and
  tasks 32 and 36.
