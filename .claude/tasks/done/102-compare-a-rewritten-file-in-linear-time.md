---
title: Compare a rewritten file in linear time
stage: I
area: lib
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: comparing a rewritten file takes linear time"
---

## Why

The code review of 2026-09-29, slice A item 5. `lib/drift.py` `changed_lines` runs `difflib.SequenceMatcher`
with `autojunk=False`, which is quadratic or worse on files of repeated lines. `verify.write` calls it on every
Write and Edit, and `cli/precommit` on every staged file. Measured on Windows on 2026-09-29, with a JSON-like
file relaid from nested to one line per record:

| Lines | Time |
|---|---|
| 2,000 | 1.77 s |
| 4,000 | 14.15 s |
| 8,000 | 112.77 s |

The hook's 2 s cap skips the checks after it, but the diff itself runs to its end in the server's worker.

## What to build

- `changed_lines` bounds its work. Past a size, such as 2,000 lines in the part that differs after the common
  head and tail, it reports the changed lines from a match on line hashes, which is linear, and never runs
  `SequenceMatcher`.
- The callers keep their messages. A result that is only approximate says so where it names lines.
- A test: 20,000 relaid lines compare in under 200 ms.

## Where

`lib/drift.py`, `checks/verify_write.py`, `cli/precommit.py`.

## Done when

- The 8,000-line case takes under 200 ms, and the existing drift tests pass.

## What changed

- `lib/drift.py`: `changed_lines` diffs exactly while the part that differs, after the common head and tail,
  holds at most `EXACT_LINES` (500) lines a side, and past that runs `SequenceMatcher` with `autojunk`, which
  matches often-repeated lines last. The task asked for a match on line hashes. `autojunk` gives the same
  speed with no second code path: a bench of 4,000 and 20,000 lines took 0.00 to 0.04 s for a relaid JSON
  file, shuffled unique lines, and 60 distinct lines mixed, where the exact diff took 21.9 s at 4,000. It
  names more lines than changed in such a rewrite, 2,284 against 571 at 4,000 relaid lines. Both callers,
  `verify.write`'s line list for a warning and `UNINTENDED_CHANGE`'s list, use the lines only to say where,
  and the warnings fire the same.
- Tests: 21,000 relaid lines compare under 0.5 s, which ran past a 90 s limit before, and two changes in a
  20,000-line file still name lines 701 and 901 exactly. The suite of 989 passes on Windows.
- `live-verify` passed on the CLI 2.1.283.
- Docs: `docs/design/architecture.md` (`changed_lines`).
- Checked on Windows on 2026-09-29.
