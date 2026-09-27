---
title: Add batch edit, splice and append
stage: F
area: mcp
created: 2026-09-27
status: open
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
| Append a dated entry | `tlog.py` ran 420 times |

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

All three call `lib`: the profile, the atomic write, the file lock and the anchor matching. None of these tools
gets a copy of its own.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_edit.py`, `tests/mcp/test_tools_edit.py`.

## Done when

- Tests reproduce what the most common `edit()` variants did (`baseline/io_traps.html`, "What the agents
  built"), on CRLF, LF and BOM fixtures, in CI on both platforms.
- An interrupted write never leaves a truncated file (BYT-9).
- Two processes editing one file through `io.edit` at once both land, one after the other.
