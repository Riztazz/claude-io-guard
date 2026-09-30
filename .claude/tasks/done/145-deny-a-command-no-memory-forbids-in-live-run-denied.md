---
title: Deny a command no memory file forbids in live-run-denied
stage: I
area: infra
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: live-run-denied asks for a command the model runs"
---

## Why

Low. `live-run-denied` in `tools/probes/run_probe.py` asks the model to run `git push origin main` through
io.run, under a deny rule for `Bash(git push *)`, and passes when the session shows
`RULE_DENIED: io.run would run git push origin main`. The probe's session loads the lead's own
`~/.claude/CLAUDE.md`, which forbids a push without the lead's grant. On 2026-09-29, during task 129, the model
(claude-haiku-4-5, Claude Code 2.1.283) called no tool at all and answered that the lead's CLAUDE.md forbids the
push. The verdict read FAIL, although the run said nothing about io-guard, and `run.rules` went untested
live. Run `workbench/probes/live-run-denied/20260929-211821` holds the transcript.

Task 126 gave a run whose model skips the step the probe needs a "no verdict" (`NoVerdict`), and this probe
still reads FAIL for one.

## What to build

- The probe denies and asks for a command no memory file is likely to forbid, such as a
  `Bash(git ls-remote *)` deny rule and `git ls-remote origin`, and its verdict matches that command.
  `live-run-asked` and `live-run-wrapped` share `RUN_RULES`, so they move with it.
- A run with no io.run call raises `NoVerdict`, naming the missing call.

## Done when

- `tests/test_probes.py` covers the no-call run as no verdict.
- `python tools/probes/run_probe.py run live-run-denied`, then `verdicts`, reads pass on Windows.

## What changed

The claims held.

- `RUN_RULES` denies `Bash(git ls-remote *)` in place of `Bash(git push *)`, and keeps the `Bash(git fetch *)`
  ask rule. `git ls-remote` only reads a remote, and the probe's folder has no remote, so it changes nothing
  even if the rule failed.
- `live-run-denied` asks for `io.run` of `git ls-remote origin`, and `live-run-wrapped` for `bash -c "git
  ls-remote origin"`. `live-run-wrapped`'s prompt no longer grants a push, which it had needed.
- `run_denied` is the verdict: a run whose model called `io.run` nowhere raises `NoVerdict`, naming the missing
  call, and otherwise it looks for `RULE_DENIED: io.run would run git ls-remote origin`.

The tests, in `tests/test_probes.py`: a run with no `io.run` call reads "no verdict" and says why, where it read
FAIL before. The rule and the verdict pass for a denied `git ls-remote origin`. Both failed first.

Evidence:

- `python tests/run_all.py`: 1,132 tests, OK, 2 skipped, against 1,130 at task 146.
- `live-run-denied` passed on the CLI 2.1.283, where it read FAIL on 2026-09-29, and `live-run-wrapped` and
  `live-run-asked` passed with the new rules.

Docs: none needed.

Checked on Windows 10 on 2026-09-30.
