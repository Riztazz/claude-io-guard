---
title: Survive a broken .editorconfig or Python file
stage: I
area: lib
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: a broken .editorconfig or Python file no longer stops a check"
---

## Why

The code review of 2026-09-29, slice B items 12 and 13. Rerun on Windows on 2026-09-29.

- `lib/editorconfig.py` `matches` raises `re.PatternError` for the globs `*.{py`, `a[]b` and `[z-a]`, so
  `conform.write` ends in `GUARD_ERROR` in any repository whose `.editorconfig` holds one. A UTF-8 BOM before
  `root = true` makes the key `\ufeffroot` and drops the first `[*]` section. `indent_size = \u00b2`, a
  superscript two, passes `isdigit()` and then `int()` raises `ValueError` in `lib/profile.py`.
- `lib/code_tokens.py` `python_tokens` catches only `TokenError` and `SyntaxError`. `"a\r\u00e9"` and
  `"# c\r\u00e9\n"` raise `UnicodeDecodeError` from the 3.14 tokenizer, a lone surrogate
  `UnicodeEncodeError`, and fuzzing hit a `SystemError`. `io.compare` in code mode then errors, and one such
  file stops the whole batch.

## What to build

- Task 101 replaced the glob's regex with a matcher of its own, so `*.{py`, `a[]b` and `[z-a]` no longer
  raise: an open brace is a plain character, and an empty or backward class holds nothing. What is left: a
  BOM at the start of `.editorconfig` is dropped, and `indent_size` takes ASCII digits only.
- `python_tokens` catches every exception the tokenizer raises, and the file compares as text, with a note.
- A test per input.

## Where

`lib/editorconfig.py`, `lib/profile.py`, `lib/code_tokens.py`.

## Done when

- Each input gives a result, never `GUARD_ERROR`.

## What changed

- `lib/editorconfig.py`: `parse` drops a BOM at the start of the file, so `root = true` on the first line
  still counts.
- `lib/profile.py`: `target_profile` reads `indent_size` only when it is ASCII digits. A superscript two
  raised `ValueError`, and an Arabic-Indic four read as a width of 4.
- `lib/code_tokens.py`: `python_tokens` falls back to hash comments on any exception the tokenizer raises.
  The fallback keeps `how` as `code`, as the unclosed-bracket case already did, with no separate note.
- Tests, each failing first: a BOM before `root = true` (`tests/lib/test_editorconfig.py`); `indent_size` of
  U+00B2, U+0664, `tab` and empty (`tests/lib/test_profile.py`); `a\r` with U+00E9, a comment line with a lone
  CR before U+00E9, and a lone surrogate (`tests/lib/test_code_tokens.py`). The suite of 1,033 passes on
  Windows, 2 skipped.
- `live-conform` passed on the CLI 2.1.283.
- Docs: none describe these parsers' edge cases.
- Checked on Windows on 2026-09-29.
