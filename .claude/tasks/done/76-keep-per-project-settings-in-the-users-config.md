---
title: Keep the user's per-project settings in the user's own config, where they may loosen a check
stage: I
area: lib
created: 2026-09-29
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [74]
findings: []
platforms: [windows, macos]
commit: "feat: your own per-project settings may turn a check off"
---

## Why

On 2026-09-29 the lead could not turn `commit_policy.ascii_only` off for one project while it stayed on for the
rest. The page's project column wrote the repository's `.claude/io-guard.json`, which may only tighten, since
any cloned repository can ship one. The lead's call: "user should be able to tweak it as he wants to use it".

## What to build

Phase 1, the loader and `io.config`:

- A new layer, `Scope.USER_PROJECT`: the entry for this project under `projects` in the user's `config.json`,
  keyed by the project's absolute folder, as `verify` keys its per-project commands. It is the user's own file,
  so it may set anything the user's file may, loosening included.
- The order: defaults, the user's file, the repository's two files, then the user's entry for the project. The
  user's own choice for a project wins over the repository's file.
- The user's file is validated whole, its `projects` entries included, and dropped whole on any error, as now.
  A project file still restricts and never widens.
- `io.config` takes a third scope, `user_project`, which writes the entry for the call's project.

Phase 2, the page:

- The "Only <project>" column writes `user_project`. With nothing set there, it shows the value the project
  takes, greyed: from the repository's file when that sets one, and says so, else from All projects.
- `project_forbids` no longer greys a value in that column, since the user's file may loosen.

Phase 3: the docs, D37 in context.md, and a live check that a session turns a check off for one project only.

## Where

`plugins/io-guard/scripts/ioguard/lib/config.py`, `lib/context.py` (`config_layers`),
`mcp/tools_dashboard.py`, `ui/dashboard.html`, `docs/design/architecture.md` (section 5), `README.md`.

## Done when

- With All projects on and the project's entry off, a hook call in that project runs without the check, and
  one in another project runs with it.
- The page's project column turns `commit_policy.ascii_only` off for one project.

## What changed

- `lib/config.py`: `Scope.USER_PROJECT`, and `ConfigLayer.project` naming the folder whose entry the layer reads.
  `Scope.project` now means a file in the project's folder only. `validate` checks the user's `projects`
  entries with the file, each error named `projects.<folder>.<key>`, and `load` reads the entry through
  `project_key`, which matches folders with `paths.resolved`. `USER_FILE` names the `projects` route.
- `lib/context.py`: `config_layers` adds the user's entry last, after the repository's two files.
- `lib/config_edit.py`: `entry_of` and `with_entry`, which read and write one project's entry, pruning it and
  `projects` when they empty.
- `mcp/tools_dashboard.py`: `io.config` scope `user_project`. A refusal at `project` names it as the fix. The
  page's rows carry `own`, and no longer `project_may_set` or `project_forbids`, which the page stopped using.
- `ui/dashboard.html`: the project column writes `user_project` and shows where an inherited value comes from.
  `control` lost its `forbids` argument and `sameValue` went, both dead.
- `tools/probes/run_probe.py`: `live-own-project`, and a `user_config` may name the run's folder as `{work}`.
- Tests: `tests/lib/test_config.py` (off here and on elsewhere, the entry over the repository's file, a bad entry
  dropping the file), `tests/mcp/test_tools_dashboard.py` (the write and its remove, the refusal's fix, a hook
  call in each of two projects, the page's rows).
- Docs: `.claude/tasks/context.md` (D37), `docs/design/architecture.md` (the layers, `io.config`, the page),
  `README.md` (per-project settings, `io.config`, the page), `docs/live-checks.md` and `docs/compat.md`.

Evidence:

- `python tests/run_all.py` ran 911 tests, all passing, up from 904.
- `live-own-project` passed on Claude Code 2.1.283: with `ascii_only` on in the user's file and off in the entry
  for the session's folder, `git commit -m 'feat: caf<e-acute>'` landed with no `COMMIT_POLICY`. The control,
  `tools/ioguard.py check` on the same command in a temp repository, answered deny with `COMMIT_POLICY` without
  the entry and observe with it.
- The page from this checkout in the browser pane, over copies of the lead's configs: Ascii only showed "Set by
  the repository's .claude/io-guard.json", and Change for this project then the switch turned it off with no
  refusal. The copy's `config.json` gained the entry, and the copied repository file stayed as it was.
- Not run: the probe on the desktop app's 2.1.281, and a screenshot, since the pane sat at 320 by 182 pixels.
  macOS waits in task 36.
