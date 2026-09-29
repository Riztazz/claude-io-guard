---
title: Decide whether a project file may set a rewrite mode to allow, and tell the user what a project turned off
stage: H
area: lib
created: 2026-09-29
status: done
depends-on: [80]
findings: [security-review-2026-09-29-3]
platforms: [windows, macos]
commit: "fix: a project file cannot approve a command for the user"
---

## Why

Fable's security review of 2026-09-29, finding 3, high, checked in the code the same day. Since task 80 a
project's `.claude/io-guard.json` may set `transport.rewrite_mode.*`. With a mode of `allow`,
`plugins/io-guard/scripts/ioguard/hooks/answer.py` answers `permissionDecision: "allow"` for any Bash command
io-guard rewrote, so Claude Code's own permission prompt is skipped for it. A cloned repository can therefore
approve commands for the user, which is more than changing what io-guard checks. The same file can turn off
`shell.writes`, `commit.policy` and telemetry, zero the budgets so every check is skipped, and the user is never
told.

The lead decided on 2026-09-29 that a project file overrides any setting (D38). This task puts the one case
that approves commands back to the lead before anything changes.

## The decision for the lead

- A: `transport.rewrite_mode.*` becomes user-only, `project_may_set=False`, like the three keys D38 keeps.
- B: a project may set it, and `allow` from a project file reads as `ask`.
- C: keep D38 as it is.

The lead picked A on 2026-09-29.

## What to build, whatever the choice

- One message per session, to the user, naming each check and limit the project's file turned off or loosened
  against the user's own file.

## Done when

- The lead picked A, B or C, it is built and tested, and the session message names a project's changes once.

## What changed

- `lib/config.py`: every `transport.rewrite_mode.*` key is `project_may_set=False`, and its help says why. A
  project file that sets one is dropped whole with that error, as for the other user-only keys.
- `lib/config.py`: `load` keeps the values in force before the first project layer, and
  `LoadReport.changed` holds each key whose value the project's files change. `LoadReport.user_message` adds
  one line after any dropped-file error, naming up to `CHANGES_NAMED` (8) changes beside the user's value, a
  list or an object by its size. The hooks already give that message once per session and project.
- The message names every change, not only the ones that loosen. Which way loosens differs per key, and a
  change the user did not make is worth a line either way.
- Docs: `docs/design/architecture.md` (the user-only keys and the message), `README.md`, the drawing's
  dashboard hover text (XML and ASCII checked), and D43 in `context.md`.

Evidence:

- `python tests/run_all.py`: 953 tests, OK, up from 951. New: a project's `allow` is an error and the user's
  `ask` stays in force. A project changing three settings and naming a verify command gives a message naming
  the three with the user's values, and not the waiting command. A project value equal to the user's says
  nothing.
- On this repository's own `.claude/io-guard.json`, the message names 6 changes, from
  `checks.commit.policy.enabled false (yours true)` to `commit_policy.forbid a list of 3 (yours a list of 2)`.
- Live, Claude Code 2.1.283 on Windows: `live-project-override` passes (20260929-131702), and its SessionStart
  hook answered `This project's .claude/io-guard.json changes 1 of your io-guard settings here:
  commit_policy.ascii_only false (yours true).` once.

Checked on Windows 10 on 2026-09-29. Not checked: macOS (task 36).
