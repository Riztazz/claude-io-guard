---
title: Verify every write after it lands
stage: C
area: bytes
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-27
depends-on: [15, 17]
findings: [BYT-1, BYT-3, BYT-6, BYT-7, BYT-11, BYT-13, VFY-1, VFY-2, VFY-3, VFY-4, VFY-5, SHL-7, GIT-9]
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

## What changed

Checked on Windows 10 on 2026-09-27, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **`checks/verify_write.py`, `verify.write`.** PreToolUse Edit and Write keep a `Snapshot` by tool_use_id: the
  file's profile, its bytes up to `snapshot_bytes` (2 MB), and the input after conform. PostToolUse reads the file
  again. While `repair` is on, a dropped BOM and a changed single ending style go back on, reported as
  `EOL_CONVERTED` or `BOM_RESTORED` with "Read the file again before the next Edit". The rest is a warning that
  names its lines: `EOL_MISMATCH` and `BOM_CHANGED` when nothing was put back, `ENCODING_INVALID`,
  `CONTROL_BYTES_ADDED`, `NON_ASCII_ADDED` for the `ascii_only` extensions, `INDENT_MISMATCH`, `SIZE_COLLAPSED`
  under `collapse_percent` (50) of the bytes the call should have left, and `UNINTENDED_CHANGE` for lines outside
  the edit that differ from the text the call asked for. PostToolUseFailure drops the snapshot, and 16 are kept
  at most.
- **`checks/verify_command.py`, `verify.command`.** It runs the user's command for the file's extension after
  each Edit or Write, with no shell, under `timeout_ms` (10 s). The exit code and the first `output_chars` (2,000)
  of the output reach the model, and a quiet pass adds nothing. It is a check of its own because it starts a
  program, so the time budget can skip it without skipping the comparison.
- **The `verify` key.** User only (D24). It maps an extension to a command with `{file}`, and an absolute project
  root to its own extensions. `ConfigKey.shape` checks the inside, and a bad value drops the file like any other
  error. `lib/verify.py` holds the check and the lookup, and `paths.inside` finds the deepest project root.
- **The pre-commit script.** `scripts/precommit.py` runs the cli's `precommit` command (`cli/precommit.py`): each
  staged blob against HEAD's, through `verify_write.compare`, and exit 1 on a finding. `GitPort` gained `staged`
  and `blob`.
- **`lib/drift.py`** holds the comparison: `drift`, `edited`, `changed_lines`, `lines_holding`, `would_collapse`,
  which the plan had put in `bytesio`, and `restored`. `lib/context.py` gained `Snapshot`, `keep_snapshot`,
  `take_snapshot`, and `plugin_data`, which moved there from `hooks.entry` because the cli reads it too.
- **Six codes joined `CODES`,** all warnings: `BOM_CHANGED`, `ENCODING_INVALID`, `CONTROL_BYTES_ADDED`,
  `NON_ASCII_ADDED`, `SIZE_COLLAPSED` and `UNINTENDED_CHANGE`.
- **`tools/probes/`:** `live-verify` and `live-verify-direct`, and a setup file may sit in a subfolder.

Two choices for the lead to confirm:
- `ascii_only` defaults to empty. The design's example config lists `.md` and `.py`. As a default, that would warn
  on every non-ASCII character in any project's docs.
- `UNINTENDED_CHANGE` skips the lines new_string wrote, because the Edit tool may restyle quotes there. A Write
  gets no such allowance, because its content lands byte-exact.

Evidence:
- `python tests/run_all.py` ran 453 tests, all passing, against 400 after task 17. The byte-fault matrix injects
  5 faults into each of 12 text fixtures after a simulated Edit: control bytes, U+FFFD, a byte that is not UTF-8,
  non-ASCII, and an emptied file. Each is reported. An honest Edit of each fixture reports nothing, and each
  single-style fixture gets its endings back.
- A test installs `scripts/precommit.py` as `.git/hooks/pre-commit` in a temporary repository. A commit that turns
  CRLF into LF stops with `a.txt: EOL_MISMATCH: The staged change changed a.txt from CRLF to LF line endings.`, and
  a clean commit goes through.
- D24: a project `io-guard.json` that sets `verify` is dropped whole, its scope error names the user's
  `config.json`, and its command never starts: the marker file it would write stays absent. The user's own
  `config.json` runs the same command.
- `run_probe.py verdicts`: `live-verify` and `live-verify-direct` pass on 2.1.281 and 2.1.283 ("Hooks and MCP",
  row 29). With `conform.write` off, a Write dropped keep.txt's BOM and CRLF, `verify.write` put both back, and the
  model saw `EOL_CONVERTED: The Write tool left keep.txt with LF line endings where it had CRLF and no BOM, so
  io-guard wrote back what the file had. Read the file again before the next Edit, because io-guard changed it
  after the write.` The next Edit landed as `EF BB BF` then `GAMMA\r\ndelta`, with a Read before it and without
  one. `live-empty` and `live-conform` still pass on 2.1.283.
- Time, p50 of 5: 0.8 ms before and 6.4 ms after an Edit of 0.1 MB, 8.1 and 66.9 ms at 1 MB, and 15.4 and 32.0 ms
  at 2.15 MB, past `snapshot_bytes`, where only the profiles are compared.

Docs updated: `architecture.md` sections 1 to 6. `context.md`: "Hooks and MCP" row 29, a task 18 paragraph, and
ANC-5 in the catalog. `live-checks.md` and `compat.md`. The README's status line, a row in "What it fixes", step 5
of "How it works", and three settings: after each write, verify commands, and the pre-commit hook. `CLAUDE.md`'s
layout and a line under "Running things". The drawing needed no change: its File tools box already says io-guard
checks every write, and the pre-commit script runs outside Claude Code.

Not checked:
- macOS live, which waits in task 36 (D21). CI runs both platforms once the lead pushes. The local macOS path
  simulation cannot build an absolute root for `test_verify`'s shape cases, so those three rest on CI.
- `verify.command` in a live session. Its tests run real Python commands, but no probe named a verify command.
- Two Edits of one file in one message: whether the harness runs each call's PostToolUse before the next
  PreToolUse. The snapshots are kept by tool_use_id either way, and a change another call made in between would
  show as `UNINTENDED_CHANGE`.
- ANC-5 left this task's findings. A write that adds a private-use glyph gets no warning, because nothing marks one
  as a mistake, and the profile line after a Read names them (task 16).
- Replay was not run. These checks refuse nothing, and the corpus holds no file bytes.
