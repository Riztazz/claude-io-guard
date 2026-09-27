---
title: Diagnose failed file calls and return the fix
stage: D
area: stale
created: 2026-09-27
status: open
depends-on: [03, 15, 16]
findings: [ANC-1, ANC-2, STL-1, STL-2, STL-4, PTH-1, INP-3, INP-4, INP-5, RUN-3, LCK-1]
platforms: [windows, macos]
commit: "feat: answer every failed file call with the closest match and a corrected call"
---

## Why

Each failed file call below was followed by a re-read and a retry. Counts are from the lead's transcripts:

| Failure | Count |
|---|---|
| Anchor misses | 67 |
| Not read yet | 82 |
| Modified since read | 30 |
| Missing paths | 175 |
| Reads over the size or token limit | 11 |

The tool's error names the problem but not the fix.

## What to build

A PostToolUseFailure check on Read, Edit, Write, Grep and Glob. It picks a branch from the tool and the error
text.

- **"String to replace not found" (`ANCHOR_NOT_FOUND`):**
  - Show the closest match after normalising whitespace, with line numbers (`lib.anchors.closest`).
  - Show that region with visible markers for tab, CR, trailing space, BOM and private-use glyphs.
  - State the file's ending style.
  - When the match is exact after normalising, put a corrected `old_string` in `fix`.
- **"Found N matches" (`ANCHOR_AMBIGUOUS`):** list every match with two lines of context, and propose the
  shortest unique anchor.
- **"Modified since read" or "not read yet" (`STALE_VIEW`, `NOT_READ`):** show the current text of the region the
  edit aimed at. Say whether a shell command or a formatter touched the file (task 21).
- **Identical strings:** treat it as a freshness signal, and show the region.
- **"Does not exist" from Read, Edit, Grep or Glob (`PATH_NOT_FOUND`):** suggest the nearest existing paths by
  basename from `git ls-files`, then by fuzzy match.
- **Read over the size or token limit (`READ_TOO_LARGE`):** give a line-count outline, and suggest offset and
  limit windows.
- **Grep pattern rejected (`PATTERN_INVALID`):** give the reason, and either a rewritten pattern or the PCRE2
  flag.
- **Grep or Glob timeout (`SEARCH_TOO_BROAD`):** suggest a narrower path.
- **EPERM on Edit:** use task 19's lookup of the process that holds the file.

## Where

`plugins/io-guard/scripts/ioguard/checks/diagnose.py`, `lib/anchors.py`, `tests/checks/test_diagnose.py`.

## Done when

- Replay over the 67 recorded misses names the intended region for at least half of them. Record the measured
  rate.
- Each branch has a live check on Windows, and its tests pass in CI on both platforms.

## Notes

- **An anchor miss fires no hook after the call.** Task 03 found that an Edit whose `old_string` is missing is
  refused by the tool before it runs, as a `<tool_use_error>`, and neither PostToolUse nor PostToolUseFailure
  fires (`context.md`, "Hooks and MCP", row 5). The Edit branches therefore run in PreToolUse: the check finds
  the anchor itself, and a miss or a double match is a `deny` that carries the fix. The ambiguous-match and
  not-read-yet refusals look like the same kind of tool error, and this task confirms them live before relying
  on either hook.
- **A stale view no longer fails the Edit.** An Edit after the file changed on disk applied, with a note that the
  file was modified since it was read (row 5). `STALE_VIEW` becomes a warning after the call, fed by task 21.
- **A missing path does reach PostToolUseFailure**, with the error "File does not exist. Note: your current
  working directory is <cwd>." and its `additionalContext` reaches the model (row 5).
