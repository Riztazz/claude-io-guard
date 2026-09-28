---
title: Start Python through one launcher, named by IOGUARD_PYTHON
stage: I
area: launch
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [06, 23, 30]
findings: []
platforms: [windows, macos]
commit: "fix: start Python through one launcher, named by IOGUARD_PYTHON"
---

## Why

On 2026-09-28 the lead restarted the desktop app, and io-guard checked nothing in any desktop session after that.
The desktop passes a plugin from a local-folder marketplace, and every plugin synced from claude.ai, to each
session as `<name>@inline`. Claude Code keeps a saved plugin option under the plugin's id, so the `python`
option saved for `io-guard@claude-io-guard` never reached `io-guard@inline`. The server then started the
default, `python3`, which on Windows is the Microsoft Store stub. `context.md` has the evidence.

Fable reviewed the first plan the same day. Its findings, which the lead took as recommended:

- A saved option can't survive the desktop's renaming, whatever its type, so io-guard drops `userConfig`.
  `IOGUARD_PYTHON`, an environment variable, is the one way to name an interpreter.
- The plugin directory's checklist blocks a hook or MCP command with a variable other than
  `${CLAUDE_PLUGIN_ROOT}` for a plugin in a subfolder of its repository. `${user_config.python}` was one.
- Skipping `WindowsApps` paths guesses around the Store stub. `py -3`, which python.org installs, never meets
  it.

## What to build

- `scripts/pyrun`, POSIX sh, and `scripts/pyrun.cmd` for `cmd.exe`. Each tries `IOGUARD_PYTHON`, then on
  Windows `py -3` and `python`, and on macOS `python3` and `python`. Each looks commands up on `PATH` only, and
  with no interpreter writes one line naming the fix to stderr and exits 1.
- `.mcp.json` starts `${CLAUDE_PLUGIN_ROOT}/scripts/pyrun`, and both command hooks start
  `sh "${CLAUDE_PLUGIN_ROOT}/scripts/pyrun" "${CLAUDE_PLUGIN_ROOT}/scripts/hook.py" <event>`.
- `plugin.json` loses its `userConfig`, and `hook.sh` goes.
- `hook.py` warns once when its own Python is older than 3.14, which covers the server, started the same way.

## Where

`plugins/io-guard/scripts/pyrun`, `pyrun.cmd`, `hook.py`, `.mcp.json`, `hooks/hooks.json`,
`.claude-plugin/plugin.json`, `tests/hooks/test_launcher.py`, `tests/test_plugin_files.py`,
`tools/probes/run_probe.py`.

## Done when

- The live probes pass through `pyrun` on the CLI and the desktop's release, with nothing set.
- `IOGUARD_PYTHON` from the `env` block of the settings reaches the server.
- A desktop session starts the server after the lead's reinstall (task 41 carries that check).

## What changed

- **The launcher.** `pyrun` and `pyrun.cmd` as above. `pyrun` tells Windows by `OS=Windows_NT`. `pyrun.cmd` is
  CRLF, kept byte for byte by `*.cmd -text` in `.gitattributes`, sets `NoDefaultCurrentDirectoryInExePath` and
  asks `where` for `$PATH:` matches, so a `python.bat` in the project folder never runs. A wrong `IOGUARD_PYTHON`
  is named, parentheses in its path included.
- **The plugin.** `.mcp.json`, `hooks.json` and `plugin.json` as above. `hook.sh` is deleted, and `hook.py`
  lost its probe of the server's interpreter.
- **The probes.** The `live-*` probes pass `IOGUARD_PYTHON` in place of `pluginConfigs`. `launch-hooksh` is
  `launch-pyrun`.
- **Live, 2026-09-28, Windows 10.** `live-empty`, `live-server`, `live-server-down` and `live-answers` passed
  on the CLI 2.1.283 and on the desktop's 2.1.281. `IOGUARD_PYTHON` in `--settings` `env` reached the server
  on both, and a wrong value stopped it with the value named in the MCP log. No server process outlived its
  session. The desktop app itself waits for the reinstall in task 41.
- **Cost.** `launch-pyrun` 275.0 ms at p50, 285.8 at p95. `hook.py` started directly takes 197 ms, 156 of it
  imports, and `sh pyrun` adds 36 ms. The server starts in 395 to 411 ms through `py -3`, and 231 to 248 ms
  with `IOGUARD_PYTHON` set. `launch-mcp` gave 37.9 ms where it gave 1.2 ms on 2026-09-27: task 43.
- **Tests.** 729 before, 743 after, all passing on Windows: `test_launcher.py` 8 sh cases, 8 `cmd.exe` cases
  and 2 for `hook.py`'s warning, in place of 5 `hook.sh` cases, and `test_plugin_files.py` one more. CI runs
  the sh cases on macOS.
- **Docs.** `docs/launcher.md` rewritten, `README.md` install steps, `docs/design/architecture.md` (layout,
  config, hooks, the launcher, platforms, the drawing's text), `docs/compat.md` three rows,
  `docs/live-checks.md`, `docs/architecture.svg` (the `pyrun` box, its arrows and its step), `context.md` (D15,
  D29 and the incident), the `io-guard-dev` skill and task 36's Mac checks.
