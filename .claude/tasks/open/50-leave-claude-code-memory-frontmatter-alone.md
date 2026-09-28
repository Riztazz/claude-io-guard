---
title: Leave the frontmatter Claude Code writes in a memory file out of UNINTENDED_CHANGE
stage: I
area: bytes
created: 2026-09-28
status: open
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
