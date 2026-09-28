---
title: Leave the frontmatter Claude Code writes in a memory file out of UNINTENDED_CHANGE
stage: I
area: bytes
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
depends-on: [18, 49]
findings: []
platforms: [windows, macos]
commit: "fix: expect the memory frontmatter Claude Code writes"
---

## Why

A Write of a new memory file, `~/.claude/projects/<project>/memory/io-guard-over-scripts.md`, on 2026-09-28
got `UNINTENDED_CHANGE: Lines 3, 5, 7 and 8 of io-guard-over-scripts.md differ from what this write asked
for.` The body was intact. Claude Code's memory system rewrote the frontmatter after the write: it quoted
`description`, and added `node_type: memory`, `originSessionId` and `modified`. The warning sends the agent to
put back a change nobody should undo.

An Edit does the same. The same day, six Edits to the bodies of six memory files each got `UNINTENDED_CHANGE:
Line 8 of <file> differ from what this edit asked for.` Line 8 is `modified:`, which the harness sets to the
time of every change.

The CLICKER session's telemetry, `0184073d-fc65-49ec-ad51-ff443f3c879f`, holds the seven: one Write and six
Edits with `UNINTENDED_CHANGE`. This repository's session hit it too, on 2026-09-28 at 13:13 UTC: a Write of
`read-io-guard-report-after-each-task.md` got `Lines 3, 5, 7 and 8 ... differ`. Line 3 is `description`, now
quoted. Lines 5, 7 and 8 are the added `node_type: memory`, `originSessionId` and `modified`.

## What to build

- A memory file under `projects/*/memory/` in Claude Code's config folder takes the frontmatter keys Claude
  Code adds, and the quoting it changes, as expected. A change to its body is still reported.
- The config folder is `CLAUDE_CONFIG_DIR`, else `~/.claude`, the two `lib.context.home_folder` falls back on.
- A test from the recorded write.

## Where

`plugins/io-guard/scripts/ioguard/checks/verify_write.py`, `tests/checks/test_verify_write.py`. It changes the
same comparison as task 49, so it goes after it.

## Done when

- The Write and the Edits above get no `UNINTENDED_CHANGE`, and a write whose body the harness changed still
  does.

## What changed

- `lib/context.py`: `claude_folder(env)`, `CLAUDE_CONFIG_DIR` else `~/.claude`, which `home_folder` now builds
  on, and `memory_file(path, env)`, true for `projects/<project>/memory/<name>.md` in that folder only.
- `lib/drift.py`: `frontmatter_end(text)`, the last line of a leading `---` block, or 0.
- `checks/verify_write.py`: `Written.rewritten`, the lines at the top that Claude Code rewrites. For a memory
  note it is the frontmatter, and `UNINTENDED_CHANGE` leaves those lines out. The body is compared as before.
- Tests: `tests/checks/test_verify_write.py` (4), from this session's recorded Write of 13:13 UTC, with its
  lines 3, 5, 7 and 8. An Edit whose `modified:` moved, a body change still named, and the same frontmatter
  change outside the memory folder still named. `tests/lib/test_context.py` (2), `tests/lib/test_drift.py` (1).
- Docs: `docs/design/architecture.md` (the two `lib.context` functions and `frontmatter_end`),
  `docs/live-checks.md` and `.claude/tasks/context.md` (row 39, below).
- Evidence: `python tests/run_all.py` ran 826 tests, all passing, up from 819.

Found on the way, as row 39 of "Hooks and MCP": the rewrite is the desktop app's. A one-off `claude -p` run on
2.1.283 wrote and edited a note in its own memory folder, and the note stayed exactly as given, with no
`node_type` and no `modified`. So no `live-*` probe can show the fix, and the probe written for it was dropped.

Not checked live yet: a Write and an Edit of a memory note in the desktop app, with this build installed. That
waits for the plugin update after batch 1, and then runs in this repository's session. Checked on Windows on
2026-09-28, through the tests only.
