---
title: Fit the report's lines to its width, and count the info codes
stage: I
area: infra
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [28]
findings: []
platforms: [windows, macos]
commit: "fix: keep the report's lines whole, and count its info codes"
---

## Why

`python tools/report.py --days 1` on 2026-09-28 printed `Calls: PreToolUse 1,096, ..., PostToolUseFa` and
`Projects: ..., and 4 `. `render` cuts every line at `WIDTH`, 110 characters (`cli/report.py`, line 175), and
the `Calls`, `Tools` and `Projects` lines come from `listed`, which does not fit its names to that width. Only
the line after the code table goes through `fitted`, which keeps whole names.

The same run showed `EXIT_BENIGN` as 0, 0 and 0. The table has a column for fixed, warned and refused, and an
info code falls in none of them, so a code that fired reads as one that never did.

## What to build

- The `Calls`, `Tools` and `Projects` lines go through `fitted`, or a helper both share, so no line ends in the
  middle of a name.
- An `info` column, or the info codes counted under a name that says what they are.
- `verify.command` declares no code (`checks/verify_command.py`, line 28), so a user's own check that fails after
  a write reaches the model and never the telemetry. On 2026-09-28 its `py_compile` caught a SyntaxError an Edit
  left in `tools/probes/run_probe.py`, and the report counted nothing. Give it a code, a warning, and count it.
- Tests: a report with more names than fit, and one with an info code.

## Where

`plugins/io-guard/scripts/ioguard/cli/report.py`, `checks/verify_command.py`, `lib/results.py`, `tests/`.

## Done when

- Every line of the report ends on a whole name or a count, and `EXIT_BENIGN` shows the number of times it fired.

## What changed

- `cli/report.py`: `counted` builds the calls, tools, projects, platforms and refused-shapes lines through
  `fitted`, which keeps whole names and says how many are left out. Platforms have a line of their own.
  The code table has an `info` column. Only a GUARD_ERROR line is still cut, since its error is free text.
  `listed` is gone.
- `checks/verify_command.py`: what the verify command said reaches the model as `VERIFY_OUTPUT`, a warning
  with the command and its exit code, where it was bare context. The text the model reads is the same, with the
  code in front. The code is not `VERIFY_FAILED`, because a command that passes and prints something reports
  too.
- `lib/results.py`: `VERIFY_OUTPUT`. `tools/skill.py` wrote its row.
- Tests: `tests/cli/test_report.py` (2), `tests/checks/test_verify_command.py` (1, and its reader moved to
  the result).
- `tools/probes/run_probe.py`: `live-verify-output`.
- Docs: `docs/design/architecture.md`, `docs/live-checks.md`, `docs/compat.md`.

Evidence:

- `python tests/run_all.py` ran 847 tests, all passing, up from 844.
- `python tools/report.py --days 1` on 2026-09-28: the calls, tools and projects lines end on counts and
  "and N more", platforms stand alone, and `EXIT_BENIGN` shows 1 under `info` where it showed 0, 0 and 0.
- `live-verify-output` passed on 2.1.281 and 2.1.283, and the probes' report lists `VERIFY_OUTPUT`.
- Checked on Windows on 2026-09-28.
