---
title: Let the project's file override any setting, and run its commands only once the user approves them
stage: I
area: lib
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [76, 79]
findings: []
platforms: [windows, macos]
commit: "feat: the project file overrides any setting, and its commands wait for approval"
---

## Why

On 2026-09-29 the lead found task 76's third layer, the user's own `projects` entries, "extremely confusing":
"We have globals (in ~/.claude) and we should have .claude/io-guard.json in projects .claude. That way,
anything in .claude/io-guard.json overrides the globals for this particular project and that's it. If we ship
.claude/io-guard.json it works as is from the start." Keeping `verify` and `format` out of the project file
"will make this super unusable across multiple codebases", so a project's commands run once the user approves
them. Fable reviewed the gate the same day: an approve button on the page is not enough, since the model drives
the browser pane and holds the page's token, and the one control a model cannot press is Claude Code's own
permission prompt.

## What to build

Phase 1, two layers:

- The layers are defaults, the user's `config.json`, and the project's `.claude/io-guard.json` and
  `.claude/io-guard.local.json`. The user's `projects` entries and `Scope.USER_PROJECT` go, and the lead's
  entry for this repository moves into its `.claude/io-guard.json`.
- A project file may set any key, and its value wins: `project_forbids`, `project_narrows` and `project_joins`
  go, and a project's list replaces the user's. Two limits stay. A key that reaches every project, because it
  exports variables at session start or deletes the shared telemetry, stays the user's:
  `checks.session.probe.env`, `env_windows` and `telemetry.retention_days`. A regex that could stall is still
  refused (`project_regex`).
- `io.config` loses `user_project`, and the page's project column writes the project's file again. The line
  above the headings names both files.

Phase 2, the gate on commands:

- `verify` and `format`, the keys that make io-guard start a program, are marked `runs`. A project file's value
  for them is held, not merged, until the user approves it.
- `trust.json` in io-guard's folder holds, per resolved project root, the SHA-256 of the canonical JSON of the
  held values and when they were approved. A changed command changes the hash, and the value is held again.
- A new io tool, `io.trust`, lists the held commands. Its PreToolUse hook, a check like `restore.ask`, answers
  `ask` with the commands in the reason, so Claude Code's permission prompt shows them to the user. The tool
  writes `trust.json` only when the session recorded that ask. The prompt says when a command runs a script
  from inside the repository, which a pull can change.
- Until approved, `verify.command` and `io.format` run the user's own commands only, and say once per session:
  `PROJECT_COMMANDS_UNTRUSTED`, naming each held command and the call, `io.trust`.

Phase 3: tests, a live probe of the gate, the docs, and D38 in context.md, which replaces D24's rule for
project files and D37.

## Done when

- A project file that turns a check off, sets `rewrite_mode` to `allow`, or raises a number, takes effect.
- A project's `verify` command runs only after `io.trust` and the user's yes, and stops running when the
  command changes.

## What changed

Phase 1, two layers:

- `lib/config.py`: `Scope.USER_PROJECT`, `ConfigLayer.project`, the `projects` entries, `project_forbids`,
  `project_narrows`, `project_joins`, `widened` and `joined` went. A project file sets any key but those marked
  `project_may_set=False`, now `telemetry.retention_days` and the session probe's `env` and `env_windows`. A
  project's list replaces the user's, and a stalling regex still drops the file. `commit_policy.forbid` and
  `io.dashboard.idle_minutes` opened to project files.
- `lib/context.py`, `lib/config_edit.py`, `mcp/tools_dashboard.py`: back to the user's file and the project's,
  and `io.config`'s `user_project` scope went. `checks/verify_write.py`, `win_paths.py`, `verify_command.py`
  lost their restrict-only markers, and every list key's text says a project's list replaces it.
- `ui/dashboard.html`: the project column writes the project's file, shows "Only your own config sets this" for
  the three user-only keys, and the line above the headings names both files.

Phase 2, the gate on commands:

- `lib/config.py`: `ConfigKey.runs` marks `verify` and `format`, and `load` holds a project's values of them in
  `LoadReport.held`. `lib/trust.py`: `fingerprint`, `approved` and `approve`, over `trust.json`.
  `lib/context.py`: `trusted` merges held commands only when approved, `Context.held` carries the rest, and
  `config_stamp` watches `trust.json`.
- `checks/trust_ask.py`: `trust.ask` answers ask with `TRUST_ASKED` on `io.trust`, and `untrusted` builds the
  once-a-session `PROJECT_COMMANDS_UNTRUSTED`, which `verify.command` and `io.format` give.
  `mcp/tools_trust.py`: `io.trust`, which approves only what the hook asked about.
  `hooks/hooks.json`: the PreToolUse matcher names `io.trust`, which the first live run showed was missing.
- `lib/results.py`: the two codes, and `VERIFY_OUTPUT`'s summary no longer says "the user's".

Phase 3:

- `ui/dashboard.html`: a project command that waits says to ask for `io.trust`.
- `tools/probes/run_probe.py`: `live-trust`, `live-project-override` in place of `live-own-project`,
  `live-ascii-replaced` in place of `live-ascii-joined`, and `live-config`'s refused write now
  `telemetry.retention_days`. The `{work}` substitution went, with the probe that used it.
- Tests: `tests/lib/test_config.py` (overrides, a held command, a user-only key),
  `tests/checks/test_trust_ask.py`, `tests/checks/test_verify_command.py` (a command waits, runs once approved,
  waits again when changed), `tests/mcp/test_tools_dashboard.py`, `tests/test_plugin_files.py` (every io tool an
  ask check guards is in the PreToolUse matcher), `tests/mcp/requests/legacy.expected.json`.
- Docs: `.claude/tasks/context.md` (D38), `docs/design/architecture.md`, `README.md`, `CLAUDE.md`,
  `docs/live-checks.md`, `docs/compat.md`, `docs/architecture.svg`, and the skill's tables.

Evidence:

- `python tests/run_all.py` ran 914 tests, all passing: 913 before phase 1, 908 after it, 912 after phase 2.
- On Claude Code 2.1.283: `live-trust`, `live-project-override`, `live-ascii-replaced` and `live-config` passed.
  `live-trust`'s first run failed, since the hook matcher lacked `io.trust`: `io.trust` then refused, as built,
  and approved nothing.
- Not run: the probes on the desktop app's 2.1.281. macOS waits in task 36.
