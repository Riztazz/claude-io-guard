---
title: Keep a lone CR in written content
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: [BYT-1]
platforms: [windows, macos]
commit: "fix: a Write keeps a lone CR the content holds"
---

## Why

The code review of 2026-09-29, slice A item 21. `conform.write` converts the content's line endings to the
file's through `lib/profile.convert_eol`, which also turns a lone CR into the file's ending:
`"a\rb\r\nc\nd"` becomes `a\nb\nc\nd` in an LF file. A fixture or a CSV that holds a bare CR on purpose
changes, and the note only says the endings were converted.

## What to build

- `convert_eol` converts `\r\n` and `\n` to the file's ending and leaves a lone `\r` as it is. The lead
  decides first whether a lone CR in the content of a file that has none should instead be named in the note.
- A test with the case above.

## Where

`lib/profile.py`, `checks/conform_write.py`.

## Done when

- The case keeps its lone CR, and the conform tests pass.

## What changed

- The lead chose option 1 of 4 on 2026-09-29: keep a lone CR as written, and name it (D46).
- `lib/profile.py`: `convert_eol` converts only CRLF and LF, through `ENDING`, and leaves a lone CR. In a CR
  file every ending still becomes CR. `lone_cr_lines` gives the line of each lone CR. Since `convert_eol` is
  shared, the `verify.write` repair and the io tools' edits keep a lone CR too.
- `checks/conform_write.py`: `lone_crs` adds `EOL_MISMATCH`, `The content holds a lone CR, which ends no
  line, on line 1, and io-guard kept it as written.`, with the fix `Take it out if the line was meant to end
  or to run on, since the Read tool shows it as nothing.`, beside a rewrite or alone when nothing else changed.
  A file whose own ending is CR names nothing.
- Tests, each failing first: `convert_eol` keeps a lone CR in CRLF and LF targets and makes every ending CR in
  a CR target, where the old test said a lone CR becomes CRLF (`tests/lib/test_profile.py`); a Write of
  `a\rb\r\nc\nd\n` into an LF file lands as `a\rb\nc\nd\n`, and one of `x\ny\rz\n`, which needs no other
  change, lands as written, each with the warning naming its line (`tests/checks/test_conform_write.py`). The
  suite of 1,050 passes on Windows, 2 skipped.
- The real case: `workbench/SmartTablesHost/.../SmartTableOffscreenStage.cpp`, CRLF with one stray lone CR,
  turned to LF and repaired by `drift.restored`, now comes back byte for byte, the CR included. Before, the
  repair made that CR a line break.
- `live-conform` passed on the CLI 2.1.283.
- Docs: `docs/design/architecture.md` (the package tree, `convert_eol`, `lone_cr_lines`),
  `.claude/tasks/context.md` (D46).
- Checked on Windows on 2026-09-29.
