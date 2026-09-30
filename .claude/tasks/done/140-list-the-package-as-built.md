---
title: List the package in the design as it is built
stage: I
area: docs
created: 2026-09-29
status: done
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

## What changed

The three claims held. The line numbers had moved with the tree rows tasks 129 to 137 added, and nothing else in
the tree was out of step: after those tasks' `ports`, `folders`, `session`, `probing`, `compare`, `diagnosis`,
`writes`, `program` and `waiting` rows, these three were the only ones the package and the tree disagreed on.

- The `elicit.py` row is gone. Section 7, "Elicitation in both eras", stays as the record of the plan, and it
  already says no elicitor is built.
- `fakes.py` has a row after `ports.py`: `FakeFs` and `FakeGit`, the in-memory ports `Context.fake` builds.
- `retention.py` has a row after `telemetry.py`: `newest`, `older` and `delete`, which clear io-guard's folders
  past `io.saved_days`.

The test: `test_the_design_tree_lists_every_module_and_only_those` in `tests/test_layout.py` reads section 1's
tree and compares its module rows with the `.py` files in `lib`, `checks`, `hooks`, `mcp` and `cli`, less
their `__init__.py`. It failed on exactly the three rows first, then passed. Its second test shows the scan
counts each module under the folder row above it, in a built tree. So a module added or removed without its
row now fails the suite.

Filed: task 147. The drawing's `handles` box names an elicitor and snapshot handles, its `data` box lists
handles among the files in io-guard's folder, and the design's arrow list names two `Elicitor` arrows. None of
those is built, and the drawing is outside section 1.

Evidence:

- `python tests/run_all.py`: 1,105 tests, OK, 2 skipped, against 1,103 at task 139.
- No probe: the change is a design page and a test, and no plugin code moved.

Docs: `docs/design/architecture.md`, section 1.

Checked on Windows 10 on 2026-09-30.
