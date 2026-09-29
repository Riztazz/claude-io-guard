---
title: Keep a lone CR in written content
stage: I
area: checks
created: 2026-09-29
status: open
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
