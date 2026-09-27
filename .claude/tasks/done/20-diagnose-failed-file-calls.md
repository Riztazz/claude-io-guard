---
title: Diagnose failed file calls and return the fix
stage: D
area: stale
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-27
depends-on: [03, 15, 16]
findings: [ANC-1, ANC-2, STL-1, STL-4, PTH-1, INP-3, INP-5, RUN-3]
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

- **An anchor miss fires no hook at all, PreToolUse included.** This task confirmed it live: an Edit or Write
  that Claude Code rejects as a `<tool_use_error>` reaches no hook (`context.md`, "Hooks and MCP", row 30), so a
  PreToolUse `deny` cannot carry the fix. The lead chose to diagnose those refusals at the session's next hook,
  from the end of the transcript (D28).
- **A stale view no longer fails the Edit.** An Edit after the file changed on disk applied, with a note that the
  file was modified since it was read (row 5). `STALE_VIEW` becomes a warning after the call, fed by task 21.
- **A missing path does reach PostToolUseFailure**, with the error "File does not exist. Note: your current
  working directory is <cwd>." and its `additionalContext` reaches the model (row 5).

## What changed

Checked on Windows 10 on 2026-09-27, on the desktop app's bundled Claude Code 2.1.281 and the CLI 2.1.283, with
Haiku 4.5.

- **Which failures reach a hook, checked first.** `edit-refusals` and `other-refusals` showed that every Edit or
  Write Claude Code rejects as a `<tool_use_error>` reaches no hook, PreToolUse included. That covers not read
  yet, the anchor not found, two matches, identical strings, and an Edit of a missing file. A Read over 256 KB,
  a pattern ripgrep rejects, and a Grep path or Glob folder that does not exist fire PostToolUseFailure. The
  lead chose the next-hook diagnosis (D28) over waiting for `io.edit` and over a task of its own.
- **`checks/diagnose.py`.** `diagnose.failure` answers a failed Read, Grep, Glob, Edit or Write after the
  failure. `diagnose.refused` runs on every hook, reads the last 256 KB of `transcript_path`, and answers each
  refusal after the last call that ran, once. Both share one `Diagnosis`:
  - `ANCHOR_NOT_FOUND`: the lines old_string matches with spaces and tabs ignored, and the corrected
    old_string quoted as JSON. Otherwise the closest lines, numbered and scored. The file's ending style is named.
  - `ANCHOR_AMBIGUOUS`: each place with a line of context, and the shortest whole-line old_string that names the
    first place.
  - `STALE_VIEW`: identical strings, or a file changed after the Read, get the aimed-at lines as they are now.
  - `PATH_NOT_FOUND`: files of the same name from `git ls-files`, or from a walk of the nearest folder that
    exists, capped at 20,000 entries. A missing Grep or Glob folder gets the nearest folder that exists.
  - `READ_TOO_LARGE`: `offset` and `limit` parts of about 60 KB. `PATTERN_INVALID`: ripgrep's reason and the
    pattern with its regex characters escaped, or the look-around limit. `SEARCH_TOO_BROAD`: a narrower search.
- **`lib/`.** `anchors.py`: `find`, `blind`, `closest`, `unique_anchor`. `blind` ignores spaces and tabs through
  a plain substring search on squeezed text. `text.py`: `visible`, `snippet`, `head`, and `verify.command` now
  uses `head`. `transcript.py`: `refusals`. `bytesio.read_tail`, and `FsPort.read_tail` and `find_named`.
  `Event.transcript`. `render` puts the fix on its own line after quoted lines. Seven codes joined `CODES`.
- **`hooks.json`** passes `transcript_path` in each `mcp_tool` map, and its tool events now match Grep and Glob.
  `guard-fields` recorded the new maps, and `tests/fixtures/fields/` and the manifest hold them.
- **Not built:** `NOT_READ`, because the tool's own "not read yet" error names the Read to make (STL-2 left the
  findings). A Read that refuses a text file as binary (INP-4) had no branch in this task and left too. LCK-1 is
  task 19's `write.locks`.

Evidence:
- `python tests/run_all.py` ran 501 tests, all passing, against 467 after task 19.
- Replay, the Done-when: of the 78 anchor misses the corpus holds, 67 were found in the transcripts. For 25 of
  them the model later edited the same file, which gives the file as it was and the region meant, and `closest`
  named that region first for 19 (76%). Over every transcript on the machine: 133 misses, 39 judged, 27 named
  (69%). `closest` took 4.3 ms at p50 and 51 ms at most. A first version matched through a regular expression
  that backtracked for 2.6 s on one 27-line miss, and the squeezed search replaced it.
- `run_probe.py verdicts`: `edit-refusals`, `other-refusals` and `live-diagnose` pass on 2.1.281 and 2.1.283.
  `live-diagnose` walks nine steps, and the model saw every diagnosis before its next step, such as
  `ANCHOR_NOT_FOUND: old_string of the refused Edit matches line 4 of a.cpp once spaces and tabs are ignored.`,
  then `4| [TAB]int b = 2;` and `Call Edit again with old_string "\tint b = 2;".`. `live-empty` still passes.

Docs updated: `architecture.md` sections 1 to 4 and 6. `context.md`: D28, "Hooks and MCP" rows 30 and 31, and a
task 20 paragraph. `live-checks.md` and `compat.md`. The README's status line, the Edit example, now quoting the
real output, and its row in "What it fixes". `CLAUDE.md`'s layout. D1 to D28 in the `io-guard-dev` skill and
`.claude/tasks/README.md`. The drawing: flow A's step on what checks read now names the transcript.

Not checked:
- macOS, live or in CI until the lead pushes.
- `SEARCH_TOO_BROAD` live: no probe made ripgrep time out. The unit test uses the recorded error text.
- A subagent's refused call: its transcript and the hook's `transcript_path` for it were not probed.
- `STALE_VIEW` for a Write refused as modified since read, live. The unit path shares `stale` with the identical
  strings case, which `live-diagnose` covered.
