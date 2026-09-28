---
title: Find a file's indent step past its aligned continuation lines
stage: I
area: bytes
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [15]
findings: []
platforms: [windows, macos]
commit: "fix: take the indent step from the indent changes, not every line"
---

## Why

A Read of `tools/probes/run_probe.py` on 2026-09-28 got `io-guard: LF, UTF-8, 2 spaces, 1,223 lines`. The file
steps by 4: 468 lines sit at 4 spaces, 108 at 8 and 88 at 12. Its continuation lines align under an open bracket,
at 7, 9, 11, 13 and 15 spaces. `lib.profile.indent_of` (lines 192 to 205) takes the first step in `WIDTHS` that 80%
of all indented lines sit on a multiple of. Those odd widths push 4 under 80%, and 2 passes. In
`tests/checks/test_diagnose.py`, whose continuation lines sit at 25 spaces, no step passes and the width is None.

The width is more than a label. `conform.edit` re-indents a tab-indented `new_string` into a space-indented file
by it (`lib/indent.py`, `fitted`), and `io.edit` passes it to `edits.apply`. A tab-indented `new_string` sent to
`run_probe.py` would come out with 2-space levels inside 4-space code, which in Python breaks the nesting.

## What to build

- Take the step from the indent changes: the most common rise in indentation from one non-blank line to the next.
  A continuation line rises by an odd amount once, while every block rises by the step.
- Keep the 80% rule, or drop it, whichever the corpus's files agree with. Report the count of files whose width
  changes, with a sample checked by eye, in `## What changed`.
- Tests: `run_probe.py`'s shape gives 4, `test_diagnose.py`'s gives 4, and a 2-space YAML file still gives 2.

## Where

`plugins/io-guard/scripts/ioguard/lib/profile.py`, `tests/lib/test_profile.py`.

## Done when

- A Read of `tools/probes/run_probe.py` says `4 spaces`, and so does one of `tests/checks/test_diagnose.py`.

## What changed

- `lib/profile.py`: `rise_step`, the commonest rise among 8, 4, 3 and 2 spaces from one non-blank line to the
  next, the smaller step winning a tie. `indent_of` takes it, and falls back on the 80% rule when no line rises
  by one of those steps.
- Tests: `tests/lib/test_profile.py`, two shapes the old rule gave no width, a Python dict aligned under a
  bracket and an assertion message under a call, now 4, and a 2-space YAML file still 2.
- `tools/probes/run_probe.py`: `live-read-width`.
- Docs: `docs/design/architecture.md` (`Indent.width`), `docs/live-checks.md`, `docs/compat.md`.

Evidence:

- `python tests/run_all.py` ran 844 tests, all passing, up from 843.
- `live-read-width` passed on 2.1.281 and 2.1.283: the Read's profile line said `4 spaces, 7 lines`.
- The profile now gives `run_probe.py`, `test_diagnose.py` and `test_context.py` 4, and `ci.yml` 2.
- Over this repository's tracked files and `workbench/`, 293 files indent with spaces, and 52 change width.
  Every Python file among them goes to 4, 17 from a wrong 2 and the rest from none. The Markdown files go from
  none to 2, their list continuations. `workbench/SmartTablesHost/.../SmartTable.h` goes from none to 4, which
  its 980 lines at 4 spaces and its doc comments at 5 bear out, checked by eye.
- No corpus replay: the corpus holds calls, not the files they touched.
- Checked on Windows on 2026-09-28.
