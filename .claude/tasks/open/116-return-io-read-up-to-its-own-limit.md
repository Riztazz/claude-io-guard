---
title: Return io.read up to its own limit before the result spills to a file
stage: I
area: mcp
created: 2026-09-29
status: open
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
