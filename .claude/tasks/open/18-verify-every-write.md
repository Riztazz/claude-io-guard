---
title: Verify every write after it lands
stage: C
area: bytes
created: 2026-09-27
status: open
depends-on: [15, 17]
findings: [BYT-1, BYT-3, BYT-6, BYT-7, BYT-11, BYT-13, ANC-5, VFY-1, VFY-2, VFY-3, VFY-4, VFY-5, SHL-7, GIT-9]
platforms: [windows, macos]
commit: "feat: check each written file against its profile and repair only data loss"
---

## Why

Byte damage raises no error. Comparing the file's profile before and after a write shows it:
- a changed ending style or a lost BOM
- new U+FFFD, NUL or control bytes
- a collapsed size
- lines changed outside the edited region

The same moment is the cheapest place for per-language checks (VFY-1 to VFY-5).

A repair after the write has a cost. The harness records a file's state after its own write, so a repair moves the
file under it, and the next Edit fails with "modified since read". Conforming before the write (task 17) is the
primary fix, and a repair here is the exception.

## What to build

1. **PreToolUse Edit|Write: take a snapshot.** Keep the file's profile and its hash, plus its bytes for files under
   2 MB, in `SessionState.snapshots`.
2. **PostToolUse Edit|Write: compare against the snapshot.**
   - **Repair only where data would be lost:** a dropped BOM or converted endings that task 17 did not prevent.
     Every repair adds the line "Read this file before the next Edit", and telemetry counts it.
   - Report everything else:
     - `UNINTENDED_CHANGE`
     - `CONTROL_BYTES_ADDED`
     - `SIZE_COLLAPSED`
     - `ENCODING_INVALID`
     - `NON_ASCII_ADDED`, by the repository's policy in `io-guard.json`
     - `INDENT_MISMATCH`
3. **Per-language verify.** The user sets it per extension in their own `config.json`, and a project's
   `io-guard.json` may not set it (D24): one command, run on the changed file. A command for one project only is
   keyed in the user's config by the project's root. Examples:
   - `python -m py_compile`
   - `node --check`
   - a JSX parse
   - a Windows PowerShell 5.1 parse for scripts that ship to users (SHL-7)
   - `clang-format --dry-run` on the changed lines

   The command's output goes into `additionalContext`.
4. **Git pre-commit hook.** The same comparison module ships as an optional hook script that checks the staged diff
   (GIT-9).

## Where

`plugins/io-guard/scripts/ioguard/checks/verify_write.py`, `plugins/io-guard/scripts/precommit.py`,
`tests/checks/test_verify_write.py`.

## Done when

- Each byte fault injected into a fixture after a simulated write is reported, in CI on both platforms.
- Every repair is logged, counted and shown to the agent with the re-read line.
- Live on Windows, an Edit after a repair succeeds once the file is read again.
- **A project file that sets `verify` is dropped whole** with a scope error naming the key and the user's
  `config.json` as the place to set it, and no command from it runs (D24). A test proves both, in CI.

## Notes

- **ANC-4 is out of reach.** The Edit tool keeps a trailing space it is given. A trailing space the model was asked
  for is gone from its own call before any hook sees it, so the file matches the call and no comparison shows a
  loss (`context.md`, "Hooks and MCP", row 28). Task 17 found this on 2026-09-27.
- **Task 17 already reports `EOL_MISMATCH`**, for a Write over a file with mixed endings.
