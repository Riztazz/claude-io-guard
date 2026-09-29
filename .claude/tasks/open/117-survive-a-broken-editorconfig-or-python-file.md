---
title: Survive a broken .editorconfig or Python file
stage: I
area: lib
created: 2026-09-29
status: open
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

- A glob that does not compile matches nothing, with a debug line. A BOM at the start of `.editorconfig` is
  dropped. `indent_size` takes ASCII digits only.
- `python_tokens` catches every exception the tokenizer raises, and the file compares as text, with a note.
- A test per input.

## Where

`lib/editorconfig.py`, `lib/profile.py`, `lib/code_tokens.py`.

## Done when

- Each input gives a result, never `GUARD_ERROR`.
