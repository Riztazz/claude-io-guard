---
title: Move the mechanism checks share into lib
stage: I
area: runtime
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "refactor: the mechanism checks share moves to lib"
---

## Why

Medium. The layout rule is that `lib` is mechanism and `checks` is policy on it. Several check modules have
become libraries for other checks, for the io tools and for the cli, and one dodges an import cycle inside a
function. A test that wants the mechanism has to import a check, and the next check that needs the same
piece imports a third check.

Checks importing checks:

- `plugins/io-guard/scripts/ioguard/checks/conform_edit.py:24`:
  `from ioguard.checks.verify_write import SHOWN, listed`. `listed` (`checks/verify_write.py:62-71`) turns
  line numbers into "lines 4 and 9", which is text mechanism.
- `plugins/io-guard/scripts/ioguard/checks/touched.py:27-28`:
  `from ioguard.checks.shell_writes import located, resolve, tracked` and
  `from ioguard.checks.verify_write import Written, compare`.
- `plugins/io-guard/scripts/ioguard/checks/commit_policy.py:20`:
  `from ioguard.checks.shell_writes import Write, bash_writes, located, powershell_writes, resolve, targets`.
- `plugins/io-guard/scripts/ioguard/checks/journal_write.py:14`:
  `from ioguard.checks.verify_write import write_snapshot`.
- `plugins/io-guard/scripts/ioguard/checks/verify_command.py:12`:
  `from ioguard.checks.trust_ask import untrusted`.
- `plugins/io-guard/scripts/ioguard/checks/restore_ask.py:13`:
  `from ioguard.checks.run_rules import project_of`.
- `plugins/io-guard/scripts/ioguard/checks/trust_ask.py:70-73`: `config_keys` imports
  `default_registry` inside the function, with the comment `# the registry imports this module`.

The ways in reaching into check internals:

- `plugins/io-guard/scripts/ioguard/mcp/in_place.py:16`:
  `from ioguard.checks.journal_write import record_write`.
- `plugins/io-guard/scripts/ioguard/mcp/tools_run.py:22-23`: `compiled` from `command_results`, `judge` and
  `said` from `run_rules`.
- `plugins/io-guard/scripts/ioguard/mcp/tools_edit.py:16`: `Diagnosis, Failed, Wording` from `diagnose`.
- `plugins/io-guard/scripts/ioguard/mcp/tools_format.py:21`, `mcp/tools_trust.py:10`,
  `mcp/tools_dashboard.py:23`: `untrusted`, `listed`, `config_write` and `needs_yes` from `trust_ask`.
- `plugins/io-guard/scripts/ioguard/cli/precommit.py:15`: `Written, ascii_kept, compare` from `verify_write`.
- `plugins/io-guard/scripts/ioguard/cli/replay.py:22`: `WINDOWS_CUT, cut_applies` from `session_probe`.

`tests/test_layout.py` permits every one of these, since it checks the subpackage a module imports and not
whether the imported name decides or does. The cost is the one the engineering skill names: a function that
both decides and does gets copied, because the next caller wants the doing without the deciding, and
`resolve` in `shell_writes.py:361-377` is already called from three checks.

## What to build

- Move each piece that takes arguments and returns a result into a `lib` module named for its operation, and
  leave the check with its decision. Candidates, each with its present home:
  - `listed` and `SHOWN` (`verify_write.py:37,62-71`) to `lib/text.py`.
  - `Written`, `compare`, `ascii_kept` and `write_snapshot` (`verify_write.py:41-148`) to a `lib` module of
    the write comparison, since `touched`, `precommit` and `verify_write` all read them.
  - `resolve`, `located`, `moved_to`, `targets`, `into_folder`, `inside_folder` and `Write`
    (`shell_writes.py:58-111, 240-271, 361-393`) to a `lib` module of shell paths, taking the platform, the
    environment and the file system port as arguments rather than a `Context`.
  - `compiled` (`command_results.py:92-94`) to `lib/output.py` beside `error_lines`.
  - `record_write` (`journal_write.py:28-40`) to `lib/journal.py`, taking the folder, the clock, the session
    and the tag it reads from the context.
  - `listed` and `inside` (`trust_ask.py:31-54`) to `lib/trust.py`; `untrusted`, `needs_yes` and
    `config_write` stay policy and move only if a `lib` caller needs them.
  - `Diagnosis`, `Failed` and `Wording` (`diagnose.py:52-297`) to a `lib` module, with the two check classes
    left in `checks/diagnose.py`.
  - `WINDOWS_CUT` and `cut_applies` (`session_probe.py:32-61`) to `lib/probing.py`.
  - `project_of` (`run_rules.py:27-30`) to `lib/context.py` beside `project_root`.
- `trust_ask.config_keys` takes the key table from the context, or the registry's keys are passed in, so the
  local import goes.
- `tests/test_layout.py` gains a rule that a check module imports no other check module but `base`, so the
  next leak fails the suite.

## Where

The modules named above, `tests/test_layout.py`, and `docs/design/architecture.md` section 1 and section 4
for each module that moves.

## Done when

- The new layout test passes, with every check importing only `checks.base`, `lib` and the standard library.
- The suite passes, and a replay over the corpus shows no check's counts changed.

## What changed

Validated on 2026-09-29 before building: every import the task names was there, at the lines it names, and
the grep found no other. `project_of` read `ctx.env` as described.

The two layout tests came first and failed on exactly the 17 imports listed above:
`test_a_check_imports_no_other_check` and `test_a_surface_takes_only_the_pipeline_and_the_registry_from_checks`
in `tests/test_layout.py`. A check imports `checks.base` and `lib`. A way in takes only `checks.pipeline` and
`checks.registry`, which reaches further than the task asked, so the ways in no longer reach into check
internals either.

Where each piece went:

- `lib/text.py`: `listed` and `SHOWN`.
- `lib/compare.py`, new: `Written`, `compare`, `ascii_kept`, and `write_snapshot`, which now takes the file
  system, the path, the tool input and the two limits rather than an event and a context.
- `lib/writes.py`, new: the whole write finder from `shell_writes.py`, with `Host`, the platform, the
  environment and the file system, in place of the context. `bash_writes` and `powershell_writes` take the
  event's folder rather than the event. `checks/shell_writes.py` keeps the refusal, the warnings and
  `RUNS_GIT`.
- `lib/context.py`: `tracked(path, git, session)` and `project_of(env, fallback)`, and a `keys` field on
  `Context`: every setting by its dotted key, filled by `Context.live` from the registry's keys.
- `lib/output.py`: `compiled`.
- `lib/journal.py`: `record_write`, taking the folder, the time, the session, the project and the tag.
  `journal.write` and `mcp.in_place.journaled` both call it.
- `lib/trust.py`: `listed`, `inside` and `untrusted`, which takes the held commands and the session's
  `first_time` rather than a context.
- `lib/config_edit.py`: `needs_yes`, which takes the key table, and `config_write`. `trust.ask` passes
  `ctx.keys`, so the import of the registry inside `config_keys` is gone with the function.
  `mcp.tools_dashboard` passes the shipped keys.
- `lib/diagnosis.py`, moved with `git mv` from `checks/diagnose.py`: `Diagnosis`, `Failed` and `Wording`, with
  the file system, git and the platform in place of the context. `checks/diagnose.py` keeps the two checks.
- `lib/probing.py`: `WINDOWS_CUT`, `FIXED_IN` and `cut_applies`.
- `lib/runs.py`: `judge` and `said`.

Tests changed only where they imported a moved name: `test_diagnose`, `test_lint`, `test_session_probe`
(which now patches `probing.FIXED_IN`), `test_transport_body`, `test_trust_ask` and `test_verify_write`.
`tests/mcp/test_tools_dashboard.py` gives its fake context the shipped keys, as the server's live context has
them. The replay's fake context gets the registry's keys the same way.

Docs: `docs/design/architecture.md` section 1, the tree and the layout rules, and the two places in the text
that named `checks.diagnose.Diagnosis` and `verify_write.write_snapshot`. `.claude/skills/io-guard-dev`
layout rule 2. No drawing change: no component, flow or default moved.

Evidence, on Windows on 2026-09-29:

- The suite: 1,063 tests, 1,061 before and the two layout tests, OK with 2 skipped.
- A replay over the corpus with HEAD's code and with this change: the 7 checks that found anything have the
  same fix, refuse, warn, event, raised and candidate counts, 0 differences.
- An import scan of the package finds no import left unused.
- Live, Claude Code 2.1.283, from this checkout: `live-refuse`, `live-script-write`, `live-touched`,
  `live-diagnose`, `live-trust`, `live-config-asked`, `live-verify` and `live-commit-policy` pass.
  `live-run-denied` read FAIL without reaching io-guard: the model called no tool, because the lead's own
  CLAUDE.md forbids a push without a grant. So `run.rules` and `lib.runs.judge` are checked by their unit
  tests only, not live.

Found along the way, both filed:

- Task 144: shell.writes warned that a script copied into `workbench/`, which git ignores, is a new file git
  sees.
- Task 145: `live-run-denied` asks for a push, which the lead's CLAUDE.md forbids, and reads FAIL where it
  should read no verdict.
