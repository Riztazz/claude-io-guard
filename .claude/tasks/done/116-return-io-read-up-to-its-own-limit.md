---
title: Return io.read up to its own limit before the result spills to a file
stage: I
area: mcp
created: 2026-09-29
status: done
depends-on: []
findings: [INP-3]
platforms: [windows, macos]
commit: "fix: io.read returns up to its own character limit before it spills"
---

## Why

The code review of 2026-09-29, slice C item 13. `mcp/toolspec.py` `bounded` adds the text and its JSON copy
and holds the sum to `RESULT_CHARS`, 80,000. `io.read` puts the lines in both, so its own
`io.read.max_chars`, 60,000, never takes effect: a 50 KB file came back as a 4,000-character head and a
spill path, and a 25 KB file came back whole. The spilled result also drops the paging fields `next` and
`first_line`.

## What to build

- `bounded` measures the larger of the text and the JSON, since the model sees one of them, and each tool's
  own limit applies first.
- A spilled result keeps every field that is not the long text, so the paging fields survive.
- A test: a 50 KB file reads whole, and a 300 KB one pages with `next`.

## Where

`mcp/toolspec.py`, `mcp/tools_read.py`.

## Done when

- The two test files read as above.

## What changed

- `mcp/toolspec.py`: `bounded` holds the longer of the text and the JSON to `max_result_chars`, since the
  model sees one of them, and measures the JSON with non-ASCII kept, as Claude Code passes it on. A saved
  result keeps each structured field of 4,000 characters or fewer, beside `saved`, `chars` and `head`, so
  io.read's `first_line`, `total_lines` and `next` survive a spill.
- Tests, failing first (3 of 3), through the registry as the server answers: a 51,200-byte file reads whole,
  a 307,200-byte file comes back as its first part with `next`, and with `io.read.max_chars` at 500,000 the
  spilled result keeps `first_line`, `total_lines` and `next` (`tests/mcp/test_tools_read.py`). The suite of
  1,030 passes on Windows, 2 skipped.
- `live-server` passed on the CLI 2.1.283: `io.read` of a BOM and CRLF file came back in its result.
- Docs: `docs/design/architecture.md` (`max_result_chars`).
- Also in this commit: task 126's file, with the U+200B that the Write tool made of an escape in commit
  `a47c5d4` replaced by the words U+200B.
- Checked on Windows on 2026-09-29.
