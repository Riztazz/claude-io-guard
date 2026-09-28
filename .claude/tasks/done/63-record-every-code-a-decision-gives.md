---
title: Record every code a decision gives, not only its first
stage: I
area: telemetry
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [28]
findings: []
platforms: [windows, macos]
commit: "fix: telemetry counts every code a decision gives"
---

## Why

On 2026-09-28 this repository's session got `TOUCHED_BY_SHELL` and `SHELL_WRITE` together, from one
`shell.touched` decision after a Bash call. `python tools/report.py --days 1` then listed `TOUCHED_BY_SHELL` 29
times and no `SHELL_WRITE` at all.

`checks/pipeline.py`, where a decision is recorded, writes one telemetry line per decision, with
`decision.results[0]`'s code alone. Every later result is lost. That hides `SHELL_WRITE` and the drift codes
`shell.touched` adds after `TOUCHED_BY_SHELL`, and any second result of any check. The end-of-task report rule in
`.claude/rules/this-repo.md` reads these counts, so a code that fires second is never reviewed.

## What to build

- One line per result, each with its own code and severity, the decision's latency on the first line only, so the
  report's timings don't double. Or one line with every code in a list. Pick one, and keep `tools/report.py`
  reading the lines already written, since `TELEMETRY_SCHEMA` is read back in full.
- A test: a decision with two results records both codes, and the report counts both.
- `docs/design/architecture.md`, section 9, says which.

## Where

`plugins/io-guard/scripts/ioguard/checks/pipeline.py`, `plugins/io-guard/scripts/ioguard/cli/report.py`,
`tests/checks/test_pipeline.py`, `tests/cli/test_report.py`.

## Done when

- A `SHELL_WRITE` given second in a decision shows in the report's count.

## What changed

A second hole showed while reading the report: it never counted a rewrite. A rewrite's code sits in a line's
`fixed` list, with `code` null, and `cli/report.py` read `code` alone. The probes' telemetry held 15
`EOL_CONVERTED` rewrites that the report's fixed column showed as 0.

- `checks/pipeline.py`: `Run.record_decision` writes one line per result, each with its own code and severity.
  The first line alone carries the check's `latency_ms` and its rewrite's code in `fixed`. A decision with a
  rewrite and no result still writes one line whose `code` is null.
- `cli/report.py`: each code in a hook call's own line's `fixed`, the line with `check` null, counts once as
  fixed. A check line's `fixed` repeats it, so it isn't read. Lines written before this change read the same way,
  so the counts on disk are right too.
- `lib/telemetry.py`: the module's first line says what a line is.
- Tests: `tests/checks/test_pipeline.py` (1: two results write two lines, only the first timed) and
  `tests/cli/test_report.py` (1: a real pipeline run with a rewrite and two results counts each code once and
  the fix once, with one hook time). Both fail against the HEAD `pipeline.py` and `report.py`.
- Docs: `docs/design/architecture.md` (section 9, and the flows list), `docs/architecture.svg` (two step texts
  of flows A and D).

Evidence:

- `python tests/run_all.py` from Git Bash ran 862 tests, all passing, up from 860.
- `python tools/report.py --data workbench/io-guard-home --days 30` now shows `EOL_CONVERTED` fixed 17: the 15
  rewrites of the run lines and 2 `verify.write` repairs, against 0 before.
- The drawing parses as XML and is ASCII. Served from `docs/` on localhost, it renders, and the served file holds
  both new step texts. Clicking a flow and Play in the browser pane changed nothing on screen, so the step walk
  itself was not seen.
- The installed plugin gets the change at the next plugin update. The report's change reads today's lines
  already.
