---
title: Conform Write and Edit input to the file before it runs
stage: C
area: bytes
created: 2026-09-27
status: open
depends-on: [03, 15]
findings: [BYT-1, BYT-7, BYT-11, ANC-4]
platforms: [windows, macos]
commit: "feat: write new text in the file's own endings, BOM and indent"
---

## Why

The built-in tools change bytes the agent never asked to change. All three were verified live:
- Write turns a CRLF file into LF.
- Write drops a BOM.
- Edit cuts trailing whitespace from new_string: `one = ` became `one =`.

The baseline shows the damage: 328 git "LF will be replaced by CRLF" warnings, and 306 scratchpad scripts built only
to keep CRLF.

## What to build

These rewrites answer `allow` with `updatedInput` in every permission mode, because the harness auto-approves edits
inside the working directory anyway (`docs/design/architecture.md`, section 6).

**Check that claim live before relying on it.** An `allow` skips the prompt the user would have seen, so a
conformed Write to a file outside the working directory, or in the default permission mode, must not become an
edit nobody approved. Probe what the harness does with `updatedInput` and no `permissionDecision`. If that
applies the input and keeps the harness's own prompt, `hooks.answer` answers that way for file tools instead.
Task 08 raised this.

**PreToolUse Write:**
- **Existing file.** Convert `content` to the file's dominant line ending, restore its BOM, and keep its
  final-newline convention. Report `EOL_CONVERTED` and `BOM_RESTORED`.
- **New file.** Take the convention from `target_profile` (task 15).
- **File with mixed endings.** Do not guess. Warn with the counts.

**PreToolUse Edit:**
- **new_string ends in whitespace (ANC-4).** Find the unique match of old_string in the file. Extend both
  old_string and new_string on the right with the file text that follows, up to the next non-whitespace character.
  The call then has no trailing whitespace left to strip. Skip this when `replace_all` is true, and when the match
  is missing or not unique: the tool then fails, and task 20 diagnoses it.
- **Indentation.** Convert when all of new_string uses one indent style and its neighbours use the other, tabs
  against spaces. Otherwise warn with `INDENT_MISMATCH`.

## Where

`plugins/io-guard/scripts/ioguard/checks/conform_write.py`, `checks/conform_edit.py`, `tests/checks/`.

## Done when

- Live on Windows, two checks:
  - Write over a CRLF file with a BOM keeps CRLF and the BOM.
  - Edit with new_string `one = ` leaves `one = ` in the file.
- Tests over every fixture pass in CI on both platforms.
- Every rewrite passes the fixed-point test: conforming already conformed input changes nothing.
