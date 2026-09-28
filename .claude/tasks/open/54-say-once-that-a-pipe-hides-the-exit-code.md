---
title: Say once per session that a pipe hides the exit code
stage: I
area: transport
created: 2026-09-28
status: open
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
