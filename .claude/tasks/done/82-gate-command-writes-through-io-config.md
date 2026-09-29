---
title: Gate every write of a command or an exported variable through io.config and the settings page
stage: H
area: mcp
created: 2026-09-29
status: done
depends-on: [80]
findings: [security-review-2026-09-29-1]
platforms: [windows, macos]
commit: "fix: io.config asks before it writes a command or a variable"
---

## Why

Fable's security review of 2026-09-29, finding 1, high, checked in the code the same day. `setting()` in
`plugins/io-guard/scripts/ioguard/mcp/tools_dashboard.py` writes `verify`, `format` and
`checks.session.probe.env` into the user's `config.json` with scope `user`, and `lib/config.py` holds a `runs`
key apart only for project layers. `hooks/hooks.json` does not hook `io.config`. So a model steered by content it
read can set a program that runs on the next Edit or Write, or a variable every later Bash call gets, and nothing
asks the user. The settings page's `POST /api/setting` takes the same route with the page's token. This goes
around the trust gate task 80 built for project files.

## What to build

- A key marked `runs`, and each `checks.session.probe.env*` key, written through `io.config` at either scope,
  goes through Claude Code's permission prompt: `io_config` joins the PreToolUse matcher, a check answers ask
  naming the command or the variable, and `setting()` writes such a key only when that hook asked about that
  exact write, as `io.run` does.
- The page cannot answer that prompt, so it refuses such a key and says to ask Claude, or to edit the file.
- Tests for both routes, and `tests/test_plugin_files.py` names `io.config` among the guarded tools.

## Done when

- `io.config` with `{"key": "verify", "value": {...}, "scope": "user"}` shows the permission prompt, and writes
  nothing without the yes. `POST /api/setting` of `verify` is refused.

## What changed

- `lib/config.py`: `runs` now also marks a variable a started program reads. `checks/session_probe.py` marks
  `env` and `env_windows` with it. Their project values were already refused (`project_may_set=False`), so
  loading is unchanged.
- `checks/trust_ask.py`: `trust.ask` also answers ask with the new code `CONFIG_ASKED` on an `io.config` write
  of a `runs` key into the user's file, naming the key and the value as JSON, and records it through
  `keep_ask` under the call's tool use id (task 85). `needs_yes` and `config_write` are the one definition the
  tool and the page share.
- `mcp/tools_dashboard.py`: `io.config` writes such a key only through `take_ask`, and otherwise answers
  `CONFIG_ASKED` and writes nothing. The page's `POST /api/setting` refuses it with `CONFIG_REFUSED`, naming
  `io.config` and the user's file.
- `hooks/hooks.json`: `mcp__plugin_io-guard_io__io_config` joins the PreToolUse matcher.
  `tests/test_plugin_files.py` names it.
- `lib/results.py`: `CONFIG_ASKED`. The skill's code table is regenerated.
- One choice against the task text: a write to the project's file asks nothing. Its value of a `runs` key is
  held for `io.trust` whoever writes the file, so a second prompt there would add nothing.
- `tools/probes/run_probe.py`: `live-config-asked`.
- Docs: `docs/design/architecture.md` (io.config's Ask, the page, the matcher, the codes table, `runs`),
  `README.md`, `docs/architecture.svg` (the dashboard box's hover text, parsed as XML and ASCII, not opened in
  the browser), `docs/live-checks.md`, `docs/compat.md`, and D40 in `context.md`. CLAUDE.md needed nothing,
  since no check was added.

Evidence:

- `python tests/run_all.py`: 926 tests, OK, up from 922. New: the hook asks and only the call it asked about
  writes, for `verify` and for `checks.session.probe.env`. A declined ask lets no call with another id or none
  write. A read, a removal, a project write and another key ask nothing. The page refuses both keys with
  `CONFIG_REFUSED` and names `io.config`.
- Live, Claude Code 2.1.283 on Windows: `live-config-asked` passes (20260929-122826). The hook answered
  `CONFIG_ASKED: io.config would set verify to {".py": ["python", "-m", "py_compile", "{file}"]} in the user's
  own io-guard config.json, for every project.`, the permission prompt tool received the call, and the call
  wrote the key.

Checked on Windows 10 on 2026-09-29. Not checked: macOS live (task 36), and the page's refusal on screen. The
page shows a refusal's message beside its setting, as for every `CONFIG_REFUSED`.
