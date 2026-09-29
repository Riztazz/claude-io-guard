---
title: Show invisible characters as escapes in io-guard's messages
stage: I
area: lib
created: 2026-09-29
status: done
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

## What changed

- `lib/text.py`: `INVISIBLE_RANGES` is the one list of ranges, and `character_class` writes ranges as a
  regular expression's class. `INVISIBLE` is built from both.
- `lib/results.py`: `CONTROL` is the control characters but tab and newline, plus `INVISIBLE_RANGES`, so the
  two never drift. `DIRECTION` is gone, since the direction overrides are in the list. `escaped` writes
  `\uXXXX`, or `\UXXXXXXXX` past U+FFFF, where `\u` with five digits read two ways.
- Tests, failing first (11 of 11): U+E0041, U+200B, U+200F, U+2028, U+2029, U+FEFF, U+00A0, U+00AD,
  U+2060, U+E000 and U+F0000 each show as their escape (`tests/lib/test_results.py`). The suite of 1,027
  passes on Windows, 2 skipped.
- A quoted file line with a no-break space or a private-use glyph now shows it as an escape too, which is
  what the Read tool hides.
- `live-invisible` passed on the CLI 2.1.283 in 1 run of 3: Haiku wrote U+200B and read `INVISIBLE_ADDED`
  naming it on line 2. In the other 2 its Write held `lstrip('')`, no invisible character, so io-guard had
  nothing to name, and the verdict still said `FAIL`. Task 126 separates the two.
- Docs: `docs/design/architecture.md` (what `Result.of` escapes).
- Checked on Windows on 2026-09-29.
