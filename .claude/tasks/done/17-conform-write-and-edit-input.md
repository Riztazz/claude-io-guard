---
title: Conform Write and Edit input to the file before it runs
stage: C
area: bytes
created: 2026-09-27
status: done
depends-on: [03, 15]
findings: [BYT-1, BYT-7, BYT-11]
platforms: [windows, macos]
commit: "feat: write new text in the file's own endings, BOM and indent"
---

## Why

The built-in tools change bytes the agent never asked to change. All three were seen live:
- Write turns a CRLF file into LF.
- Write drops a BOM.
- A trailing space asked for in an Edit's new_string does not reach the file: `one = ` became `one =`. This task
  found where the space goes, in "What changed".

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

## What changed

Checked on Windows 10 on 2026-09-27, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **`checks/conform_write.py`, `conform.write`.** A Write over an existing file takes that file's line ending, BOM
  and final newline, reported as `EOL_CONVERTED`, or `BOM_RESTORED` when only the BOM changed. A file with mixed
  endings keeps the content as written, with an `EOL_MISMATCH` warning that gives the counts. A new file takes
  `target_profile` from its `.editorconfig`, then `git check-attr` eol, then up to 20 siblings with the same
  extension, 64 KB of each. With none of those, and for a binary or UTF-16 file, nothing changes.
- **`checks/conform_edit.py`, `conform.edit`.** When every indented line of new_string uses spaces and the 3 lines
  around the one match of old_string use tabs, or the other way round, new_string's indent is converted
  (`INDENT_MISMATCH`, fixed). A new_string that mixes both beside lines that don't is an `INDENT_MISMATCH` warning.
  A missing or repeated match, and replace_all, are left to the tool.
- **The ANC-4 extension was not built, because nothing reaches it.** `edit-trailing` showed the Edit tool keeps a
  trailing space it is given. The first `live-conform` run asked Haiku for `one = `, and its own `tool_use` already
  carried `one =`, so the space is gone before any hook sees the call. ANC-4 left this task's findings and task
  18's, the catalog marks it "-", and `TRAILING_WS_STRIPPED` and `anchors.extend_right` left the plan.
- **`hooks/answer.py`.** A Write or Edit rewrite answers `updatedInput` and `additionalContext` with no
  `permissionDecision`, unless a check asks or denies (D26). `write-quiet` showed the harness applies such input and
  keeps its own decision: in default mode the prompt carried the rewritten BOM and CRLF content, and the approved
  file landed as `EF BB BF` then `line one\r\nline two\r\n` ("Hooks and MCP", row 27).
- **`lib/`.** `profile.py` adds `convert_eol`, `with_bom` and `with_final_newline`, which take text.
  `editorconfig.py` is new: `parse`, `glob_pattern`, `matches`, and `properties`, which walks up the folders to
  `root = true`. `FsPort.list_dir` is new in `context.py` and `fakes.py`. `results.py` adds `EOL_CONVERTED`,
  `BOM_RESTORED`, `EOL_MISMATCH` and `INDENT_MISMATCH`. The registry runs eight checks.
- **`tools/probes/`.** The `write-quiet`, `edit-trailing` and `live-conform` probes, and the `rewrite_write_quiet`
  and `edit_trailing` answer modes, which can leave `permissionDecision` out.

Evidence:
- `python tests/run_all.py` ran 400 tests, all passing, against 383 after task 16: 8 in `test_conform_write.py`, 6 in
  `test_conform_edit.py`, 2 in `test_editorconfig.py` and 1 in `test_profile.py`. One answer test was renamed. The
  five changed test modules pass again with `Path` as a POSIX path, 45 tests.
- The fixed point: `test_conformed_content_is_a_fixed_point` and `test_the_conversion_is_a_fixed_point`.
  `test_every_fixture_gets_its_own_endings_and_bom` runs a Write over every byte fixture.
- `run_probe.py verdicts`: `write-quiet`, `edit-trailing` and `live-conform` pass on 2.1.281 and 2.1.283.
  `live-conform` loads io-guard from this checkout, reads a BOM and CRLF `keep.txt`, and writes `gamma` and `delta`
  over it in acceptEdits. The file landed as `EF BB BF` then `gamma\r\ndelta\r\n` on both releases.
- The Done-when line "Edit with new_string `one = ` leaves `one = ` in the file" holds for the tool on both
  releases. It does not hold when the model is asked for `one = `, because the model's call already lacks the space.
- Replay was not run for these checks. The corpus holds no file bytes, so both checks observe every recorded call,
  and neither refuses.

Docs updated: `architecture.md` sections 1, 2, 4 and 6. `context.md`: D26, the corrected trailing-space row, "Hooks
and MCP" rows 27 and 28, a task 17 paragraph, and ANC-4 in the catalog. `live-checks.md` and `compat.md`. The
README's status line, Write example, table row, and a paragraph under the rewrite modes. `CLAUDE.md`'s layout. The
drawing: flow A's answer step and the rewrite-mode panel. The `io-guard-dev` skill and `.claude/tasks/README.md`
now say D1 to D26. Task 18 drops ANC-4 and notes why.

Not checked:
- macOS live, which waits in task 36 (D21). CI runs both platforms once the lead pushes.
- `conform.edit` live: no probe gave the model a tab-indented file and a space-indented new_string.
- A new file's endings chosen live from `.editorconfig` or `.gitattributes`. Unit tests cover both.
