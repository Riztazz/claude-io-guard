---
title: Tell a model's miss from io-guard's in the live-invisible verdict
stage: I
area: infra
created: 2026-09-29
status: done
depends-on: []
findings: [ANC-5]
platforms: [windows]
commit: "fix: live-invisible says when the model wrote no invisible character"
---

## Why

Found in task 115 on 2026-09-29, CLI 2.1.283. `live-invisible` ran three times. Haiku's Write held
`raw.lstrip('')` in two runs, with no invisible character at all, and a U+200B inside the quotes in one. The one
with U+200B passed, and `INVISIBLE_ADDED` named it on line 2. The other two answered `FAIL`, though io-guard
had nothing to name. `invisible_named` in `tools/probes/run_probe.py` returns false both when the file holds
no invisible character and when io-guard stayed quiet about one, so a model that drops the character reads
as an io-guard failure.

## What to build

- `invisible_named` answers "no verdict" when line 2 of `strip.py` holds no invisible character, with the
  reason, and `FAIL` only when one is there and the model never read `INVISIBLE_ADDED` naming it.
- Or the probe retries its prompt, up to three runs, until the model writes one, if the runner has a way to
  say so.

## Where

`tools/probes/run_probe.py` (`invisible_named`, and `verdict` if "no verdict" needs a reason).

## Done when

- A run whose Write holds no invisible character reads as no verdict, and a run with one still passes.

## What changed

- `tools/probes/run_probe.py`: a check may raise `NoVerdict` with the step the model skipped, and `verdict`
  answers `no verdict` with that reason after the run's folder. `invisible_named` raises it when line 2 of
  `strip.py` holds no invisible character, and answers pass or `FAIL` only when one is there. The retry option
  was not built: the reason says to run the probe again, and a runner that reruns a model on its own would
  hide how often the model skips the step.
- Tests, failing first: a summary whose line 2 holds `lstrip('')` gives `no verdict` with its reason, and one
  holding U+200B still passes when the model read `INVISIBLE_ADDED` for it (`tests/test_probes.py`, the
  runner's first tests, loading it by its path). The suite of 1,054 passes on Windows, 2 skipped.
- Live, on the CLI 2.1.283: the old failing run `20260929-173519` now reads `no verdict` with the reason. Of
  four new runs, two had no invisible character and read `no verdict`, and two passed.
- Docs: none describe the runner's verdict words.
- Checked on Windows on 2026-09-29.
