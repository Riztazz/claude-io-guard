---
title: Show invisible characters as escapes in io-guard's messages
stage: I
area: lib
created: 2026-09-29
status: open
depends-on: []
findings: [ANC-5]
platforms: [windows, macos]
commit: "fix: io-guard's messages show invisible characters as escapes"
---

## Why

The code review of 2026-09-29, slice B item 7. Task 88 made `Result.of` escape control characters and bidi
overrides through `CONTROL`, but tag characters U+E0000 to U+E007F, zero-width U+200B to U+200F, U+2028,
U+2029 and U+FEFF pass through. Rerun on Windows on 2026-09-29: `Result.of(..., "a\U000e0041\u200b\u2028b")`
kept `0xe0041`, `0x200b` and `0x2028`. A file name or a command can carry hidden text into a message the model
reads.

## What to build

- `CONTROL` in `lib/results.py` takes every range `lib/text.py` `INVISIBLE` holds, from that one definition,
  so the two never drift.
- A test with each range.

## Where

`lib/results.py`, `lib/text.py`.

## Done when

- The test's message shows each character as an escape.
