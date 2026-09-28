---
title: Check that the lines an Edit changed hold what new_string asked for
stage: I
area: bytes
created: 2026-09-28
status: open
depends-on: [17, 18]
findings: []
platforms: [windows, macos]
commit: "fix: catch an Edit whose new_string would not land as given"
---

## Why

The Edit tool drops the trailing whitespace of `new_string`, as the kit's `writing-files.md` rule records. In
CLICKER on 2026-09-28 an Edit with `replace_all` turned `.Place.Branch, ` into `.Place.Branch.ToInt(), ` in
`Source/CLICKER/Tests/NetSphereReachTests.cpp`, and five lines came out as `ToInt(),1`. No code named it.
`verify.write` compares only the lines outside the edit (`checks/verify_write.py`, header lines 10 and 11, and
lines 112 to 121), so a difference inside the edited lines is never looked at, although `expected` already
holds the text the call asked for (line 43).

## What to build

- Before the run: when `new_string` ends in spaces or tabs and the file goes on past the match on the same line,
  refuse the Edit. The fix extends `old_string` and `new_string` past the whitespace. Whitespace at a line end
  is safe to lose, so it passes.
- Refuse, never warn. A PreToolUse warning cannot stop the Edit, and the model reads it only after the Edit has
  run, with the damage already on disk.
- First find out whether the hook's `tool_input` still holds the whitespace, or Claude Code strips it before
  the hook sees it. Record the answer in `docs/live-checks.md`.
- After the run: compare the edited lines with `expected` too. Forgive only what the tool restyles, its quotes
  and whitespace at a line end. Report each other difference with the line number and both texts.
- A test for each, from the recorded CLICKER call.

## Where

`plugins/io-guard/scripts/ioguard/checks/conform_edit.py`, `checks/verify_write.py`, `lib/drift.py`,
`tests/checks/`.

## Done when

- The CLICKER Edit above is refused before it runs, and the file keeps its bytes.
- With the refusal off, the same Edit gets a report after it naming the five lines.
