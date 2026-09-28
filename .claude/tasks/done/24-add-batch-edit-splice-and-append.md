---
title: Add batch edit, splice and append
stage: F
area: mcp
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [17, 18, 20, 23]
findings: [ANC-1, ANC-2, ANC-3, BYT-9, INP-4]
platforms: [windows, macos]
commit: "feat: batch edits, splices and appends that keep the file's bytes"
---

## Why

Agents rebuilt three primitives again and again, because no tool offered them:

| Primitive | How often agents rebuilt it |
|---|---|
| Batch edit | The CLICKER `edit()` helper exists in 73 different bodies across 138 scripts |
| Splice between markers | 117 scripts splice text between two `str.index` markers |
| Append a dated entry | `tlog.py` ran 183 times |

## What to build

- **`io.edit(path, edits[], expect_hash?)`**
  - Every anchor must match exactly once.
  - All edits apply in memory, and the file is written once.
  - The write is atomic through `lib.bytesio.write_atomic`, held inside `lib.locks.file_lock` from the read to the
    replace (D13).
  - The file keeps its own profile (task 15).
  - If any edit fails, nothing is written, and the result carries task 20's diagnosis of the failing anchor.
  - `expect_hash` refuses the edit when the file changed since the agent read it.
- **`io.splice(path, start, end, text, include_end?)`**: replaces the text between two unique markers.
- **`io.append(path, text, wrap_column?, date_prefix?)`**: appends the text, wrapped at `wrap_column`, in the
  file's profile.
- **Every result carries the same line:** "the built-in Edit needs a fresh Read of this file before its next use".
- **`paths.LockTable`**, moved here from task 23 with its first user: one `threading.Lock` per resolved path inside
  the server, held across the read, the profile and the write, inside which `lib.locks.file_lock` (task 23) holds
  the path against other processes.

All three call `lib`: the profile, the atomic write, the file lock and the anchor matching. None of these tools
gets a copy of its own.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_edit.py`, `tests/mcp/test_tools_edit.py`.

## Done when

- Tests reproduce what the most common `edit()` variants did (`baseline/io_traps.html`, "What the agents
  built"), on CRLF, LF and BOM fixtures, in CI on both platforms.
- An interrupted write never leaves a truncated file (BYT-9).
- Two processes editing one file through `io.edit` at once both land, one after the other.
- Live on Windows, three parallel subagents editing one file through `io.edit` serialise without a lost edit. This
  Done-when moved here from task 23, which built the server but not `io.edit`.

## Notes

- **`SHELL_WRITE` names `io.edit` once it exists.** Task 12's refusal names the Edit and Write tools only,
  because no `io.edit` existed to name. Add `io.edit`'s callable name to the fix in `checks/shell_writes.py`, for
  a command that writes several places in one file, with a test that renders it.

## What changed

Checked on Windows 10 on 2026-09-28, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **`mcp/tools_edit.py` holds `io.edit`, `io.splice` and `io.append`,** registered after `io.read`. Each holds
  the file through `paths.LockTable` and then `lib.locks.file_lock` from the read to the write, loads it,
  changes its text in memory, and writes it once through `write_atomic`, only when a byte changed. A missing
  file is `PATH_NOT_FOUND`, one past `io.edit.max_bytes` `READ_TOO_LARGE`, a read-only one `READ_ONLY`, a
  binary one or one that does not decode and encode back the same `ENCODING_INVALID`, a hash that differs from
  `expect_hash` `STALE_VIEW`, and a holder past `io.edit.wait_ms` `FILE_LOCKED`. No new code was needed. Every
  result names the lines it changed, the profile, the new SHA-256 and "The built-in Edit tool needs a fresh Read
  of this file before its next use".
- **`lib/edits.py` places a change in the LF view the Edit tool reads, and makes it in the file's own text,**
  so every ending outside the change stays, mixed and lone CR included, and new line breaks take
  `Profile.new_eol`. `apply` makes a batch in order, each `old_string` found once in what the edits before it
  left, or returns `Missed` and nothing is made. `appended` and `wrapped` serve `io.append`.
- **New text takes the indent of the lines around it,** tabs or spaces, which is part of the file's profile.
  `style`, `reindented` and `space_step` moved from `checks/conform_edit.py` to the new `lib/indent.py`, with
  `around` and `fitted`, and `conform.edit` calls them. `conform.edit` now reads the file through
  `anchors.edit_view`, which reads a lone CR as LF, as the Edit tool and `diagnose` do.
- **A failed place gets task 20's diagnosis.** `diagnose.Failed` takes a `Wording`: the subject, the argument,
  the tool a fix calls, and whether it has `replace_all`. `Diagnosis` takes `contents` in place of the file on
  disk, since a later edit fails against the text the earlier ones left. The fix is the whole `io.edit` call
  again, that edit corrected. Found live: with no close lines, the refusal fell back to the code's own advice,
  "Call Edit again", so that branch now carries a fix naming the tool to retry.
- **`io.read` returns `sha256`,** which `expect_hash` compares. `Profile.codec` reads the bytes whole, and
  `io.read` uses it too.
- **`SHELL_WRITE` names `io.edit`** for `sed -i`, `perl -i` and a script body, the writes that change a file in
  several places. `callable_name` moved to `lib.results`, so a check can name an io tool without importing
  `mcp`.
- **`lib.locks.file_lock` keys its lock file by `paths.resolved`,** the path through every link, as
  `LockTable` does, so two names for one file share its lock.
- **Choices made here:** a batch is sequential, as the baseline helpers were. `io.splice` takes a unique start
  and the first end after it, since agents' end markers, such as the next heading, repeat. `io.append` keeps a
  file with no last line break that way, and wraps at the `.editorconfig` `max_line_length` when no column is
  given. With no plugin data folder, the lock files go under the system temporary folder's `io-guard`. The
  design's `paths.same_file` was never built and no task plans it, so it left the design.
- **Found live: models passed each result's `sha256` back as `expect_hash` unasked,** which made three parallel
  subagents refuse each other with `STALE_VIEW`. The field docs now name it as an opt-in guard, and the result's
  hash no longer says it is for the next call.
- **Filed task 38:** no io tool writes a telemetry line, `io.read` included, though section 9 and the drawing
  say each call does. It lands before task 28, which reports from telemetry.

Evidence:
- `python tests/run_all.py` ran 623 tests, all passing, against 585 after task 23. `test_tools_edit.py` has 20,
  `lib/test_edits.py` 8 and `lib/test_indent.py` 3. They reproduce the baseline `edit()` on the `crlf`, `lf`,
  `bom-crlf` and `bom-lf` fixtures and `tlog.py` on a CRLF and an LF log, byte for byte, and cover the mixed,
  lone-CR, cp1250 and UTF-16 files.
- Two threads, and two processes started together, each made 40 `io.edit` calls on one file, and both counters
  reached 40. With the locks taken out, both tests lost edits in 3 runs of 3, as `A=0\nB=40\n`.
- An `os.replace` interrupted by a `KeyboardInterrupt` left the file's old bytes and no temporary file (BYT-9).
- `live-edit-parallel` passes on 2.1.281 and 2.1.283. Three subagents started in one message made 30 `io.edit`
  calls with no error, interleaved in the stream as A, B, A, C, B and on, and `counters.txt` ended as
  `EF BB BF` then `A=10\r\nB=10\r\nC=10\r\n`. `live-server` and `live-empty` still pass on 2.1.283.

Docs updated: `architecture.md` sections 1, 2, 4, 5, 7 and 8, with a new part on the three tools. The README's
status line and io tools. `compat.md` and `live-checks.md`. `context.md`: row 35 and a task 24 paragraph.
`CLAUDE.md`'s layout. The drawing needed no change: its io tool box and flow already name the three tools, the
anchors, the lock and the atomic write.

Not checked:
- macOS, live or in CI until the lead pushes. Task 36 holds the macOS live check of the lock.
- `io.splice` and `io.append` live. The probe calls `io.edit` only, and the other two share its path from the
  lock to the write.
- A write cut off by a killed process. The test interrupts `os.replace` inside the process.
