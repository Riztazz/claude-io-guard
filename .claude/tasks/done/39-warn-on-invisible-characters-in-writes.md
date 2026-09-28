---
title: Warn when a write adds an invisible character
stage: C
area: bytes
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [16, 18, 24]
findings: [ANC-5, BYT-13]
platforms: [windows, macos]
commit: "feat: name the invisible characters a write adds to a text file"
---

## Why

A tool's input travels as JSON, and JSON decodes an escape such as backslash-u FEFF into the character
itself. On 2026-09-28, during task 26, a Write of `tests/mcp/test_tools_format.py` meant to put the six-character
escape for U+FEFF inside two Python strings. The file got the character instead, as the bytes `EF BB BF` in the
middle of lines 40 and 76. Nothing said so. The Read tool shows the line as if the character were not there,
and only a scratchpad lint that counts bytes over 127 found it.

The same route carries U+200B and the other zero-width characters, U+00A0, U+00AD, and the bidi controls
U+202A to U+202E and U+2066 to U+2069, which make code read differently from how it runs. None is a BOM,
because a BOM sits at the start of a file, so no BOM check sees one. `NON_ASCII_ADDED` (task 18) names them only
in the extensions a user lists in `checks.verify.write.ascii_only`, and that list is empty by default.

## What to build

- **`verify.write` warns, by default and in every text file, when a write adds an invisible character**: Unicode
  category Cf, U+00A0, U+00AD, or a character from `lib.text.visible`'s list. The warning names the line, the
  character as `[U+FEFF]`, and the escape the language uses, when the file's text around it is a string
  literal. A BOM at byte 0 of a file that already had one is not added.
- **The io tools say the same in their result** when `io.edit`, `io.splice` or `io.append` add one.
- **A config key lists the characters a project allows**, such as U+00A0 in a translation file.
- **No fix.** Whether the file wants the character or its escape is the author's call (D6).

## Where

`plugins/io-guard/scripts/ioguard/checks/verify_write.py`, `lib/text.py`, `mcp/in_place.py`, their tests.

## Done when

- A replay counts the recorded Edit and Write inputs that add an invisible character, and the task's
  `## What changed` gives the number and reads every warning on a call that ran.
- A live probe on Windows: a Write whose JSON input decodes to a U+FEFF inside a Python string gets the warning
  with the line number, on the CLI and the desktop's release.

## What changed

- **`INVISIBLE_ADDED`**, a new warning code. `verify.write` reports it by default in every text file when a
  write adds a character the Read tool shows as nothing, naming each as `[U+FEFF]` with the first line that
  holds it, and the fix: write the escape with its backslash doubled in the tool call. The pre-commit script
  runs the same comparison on staged changes. `io.edit`, `io.splice` and `io.append` name the same in their
  result's `invisible` list.
- **`lib.text.INVISIBLE` and `invisible_added`**: every Unicode `Cf` character, 170 in Unicode 16.0, U+00A0,
  U+2028 and U+2029, and the private-use planes. A character counts only when the write added more of it than
  the file held, and a BOM at the start of a file is the file's, not text. A test checks the ranges against
  every `Cf` character in the running Python's Unicode tables.
- **`invisible_allowed`**, a global key, lists the characters a project adds on purpose, such as `U+00A0`.
- **The escape in the fix text is described, not shown.** A single backslash in an example would show the
  model the very escape that turns into the character.
- **No fix is made** (D6): the author decides between the character and its escape.
- Tests: 709 before, 715 after, all passing, from `python tests/run_all.py`: `test_text.py` 3, including the
  `Cf` coverage, `test_verify_write.py` 2 and a zero-width space in every fixture, `test_tools_edit.py` 1.
- **Evidence.** Over the corpus, 4 of 23,717 recorded Edit and Write calls added an invisible character, and
  all 4 ran: three literal U+FEFF inside Python strings where the escape was meant, in OrbitalDrift scripts,
  and one literal U+00A0 in a map of typographic characters. Each is a warning a reader wants. None added a
  private-use glyph. `live-invisible` passed on the CLI 2.1.283, where Haiku wrote the U+FEFF and read
  `INVISIBLE_ADDED: This Write added [U+FEFF] on line 2 to strip.py`, and on the desktop's 2.1.281, where it
  wrote a U+200B instead and read the warning naming `[U+200B]` on line 2. The verdict takes any invisible
  character on line 2 for that reason.
- **The trap struck while building this task:** in the README, the Edit tool turned a written escape into
  the character. The lint found it, and the sentence now says it in words.
- **Docs:** `docs/design/architecture.md` sections 1, 2, 4 and 5, the README's "After each write",
  `docs/compat.md`, `docs/live-checks.md`, and `context.md` (ANC-5 and BYT-13 now name task 39). The drawing
  names no single warning.
- Checked on Windows on 2026-09-28. macOS waits in task 36.
