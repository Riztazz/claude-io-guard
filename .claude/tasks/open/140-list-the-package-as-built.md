---
title: List the package in the design as it is built
stage: I
area: docs
created: 2026-09-29
status: open
depends-on: []
findings: []
platforms: [windows, macos]
commit: "docs: the design's package tree matches the package"
---

## Why

Low. `docs/design/architecture.md` section 1 is the tree every task builds from, and `.claude/rules/docs.md`
says a change updates it when the package layout changes. It differs from the package in three rows.

- `docs/design/architecture.md:121` lists `elicit.py  Elicitor, LegacyElicitor, ModernElicitor, when a
  client shows a form`. No such file exists under `plugins/io-guard/scripts/ioguard/mcp/`, and
  `git log --all -- plugins/io-guard/scripts/ioguard/mcp/elicit.py` prints nothing, so none was ever
  committed. Line 1707 of the same document says "No elicitor is built yet, because no tool needs one", so
  the tree shows as present what the text says is planned.
- The tree omits `plugins/io-guard/scripts/ioguard/lib/fakes.py`, the in-memory ports `Context.fake`
  builds, which line 375 names as `lib.fakes`.
- The tree omits `plugins/io-guard/scripts/ioguard/lib/retention.py`, which line 1796 names as
  `lib.retention`.

A reader who takes the tree as the package looks for a module that is not there, and misses two that are.

## What to build

- The tree names `fakes.py` and `retention.py` with one line each, in the style of the rows around them.
- The `elicit.py` row either goes, with the section 7 text left as the record of the plan, or is marked as
  not built, in the same words line 1707 uses.

## Where

`docs/design/architecture.md` section 1.

## Done when

- Every `.py` under `plugins/io-guard/scripts/ioguard` has a row in the tree, and every row names a file
  that exists or says it is planned.
