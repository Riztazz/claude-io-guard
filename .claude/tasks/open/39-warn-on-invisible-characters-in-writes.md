---
title: Warn when a write adds an invisible character
stage: C
area: bytes
created: 2026-09-28
status: open
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
