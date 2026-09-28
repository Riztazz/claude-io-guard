---
title: Find a file's indent step past its aligned continuation lines
stage: I
area: bytes
created: 2026-09-28
status: open
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
