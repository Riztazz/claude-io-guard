---
title: Say once per session that a pipe hides the exit code
stage: I
area: transport
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [13, 22]
findings: []
platforms: [windows, macos]
commit: "fix: warn once per session that a pipe hides the exit code"
---

## Why

`shell.lint` warns before every Bash call that pipes a build or a test into another command:
`PIPE_HIDES_EXIT: This command pipes python -m unittest into tail, so the exit code shown is tail's`
(`checks/lint.py`, `hidden_exit`, lines 169 to 180). It keeps no count, so the same sentence goes out on every
such call.

This repository's session `7eeb509f-baa1-4e42-8aec-4f8fd98fdc99` got it 35 times on 2026-09-28, and changed no
command after any of them. The warning had become noise. `shell.results` gave the same code after the run 15
times, and each of those named the failing test or the exception the pipe hid. That one did its job.

A warning an agent reads 35 times and never acts on teaches it to skip the next one.

## What to build

- The pre-run warning goes out once per session, through `ctx.session.first_time`.
- The after-run warning in `checks/command_results.py` stays as it is, since it names what the pipe hid.
- A replay over the corpus, with the pre-run count per session before and after, in `## What changed`.
- Tests: two piped test runs in one session get the pre-run warning once. A second session gets it again.

## Where

`plugins/io-guard/scripts/ioguard/checks/lint.py`, `tests/checks/test_lint.py`.

## Done when

- A session with many piped test runs gets the pre-run `PIPE_HIDES_EXIT` once, and every after-run
  `PIPE_HIDES_EXIT` as before.

## What changed

- `checks/lint.py`: `hidden_exit` returns the build and the command it pipes into, or None, and adds nothing.
  `Lint.bash` warns with it only the first time a session pipes a build, through
  `ctx.session.first_time("pipe-hides-exit")`. `shell.results` is unchanged.
- Tests: `tests/checks/test_lint.py`, a session that pipes twice warns once, and a new session warns again.
- `tools/probes/run_probe.py`: `live-pipe-once`, and `context_count`, which `context_reached` now reads.
- Docs: `docs/design/architecture.md` (the layout line), `docs/live-checks.md`, `docs/compat.md`.

Evidence:

- `python tests/run_all.py` ran 833 tests, all passing, up from 832.
- `live-pipe-once` passed on 2.1.281 and 2.1.283: two piped runs, one warning before them. `live-results`
  passed again on 2.1.283, so the warning after a run still names what the pipe hid.
- The corpus of 2026-09-27 holds 58,779 Bash calls, and none pipes a command from the default build list, so
  its count is 0 before and after. The lead's projects build through their own commands, which a project's
  `build_commands` names. This repository's session of 2026-09-28 got 35 before its runs, and would get 1.
- Checked on Windows on 2026-09-28.
