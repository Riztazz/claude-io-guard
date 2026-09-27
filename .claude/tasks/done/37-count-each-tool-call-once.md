---
title: Count each recorded tool call once, in the corpus and in the baseline
stage: A
area: infra
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [09]
findings: []
platforms: [windows, macos]
commit: "fix: count each recorded tool call once"
---

## Why

The replay corpus counts one tool call once for every transcript file that holds it. A resumed session writes its
history into a new file, and the copies keep the original `sessionId`, so one call can sit in several files and
several times in one file. Task 13 found this on 2026-09-27: the corpus built that day holds 180,478 records but
110,379 distinct tool use ids. 24,559 ids appear more than once, and the copies add 70,099 records, 39%. No id
spans two sessions. One call, `toolu_01UW16WUgqLBGncmWNHeckZ5`, sits in two CLICKER transcripts, 10 lines in
each, and became 8 records.

The baseline of 2026-09-27 (`baseline/tx_scan.py` and its siblings) reads the same transcripts the same way: its
Bash count, 97,579, is within 1% of the corpus's 98,272. So every per-call number in `context.md`'s Baseline
section, in the README's "What it fixes" table and in the tasks counts copies. A rate between two such counts is
roughly right. A count on its own is not.

## What to build

1. **`cli/corpus.py`:** `build` keeps the first record of each tool use id within a project and skips the rest.
   The index counts the skipped copies, as `copies`, beside `unpaired` and `unreadable`.
2. **A test** that builds a corpus from two transcript files holding the same call, and gets one record.
3. **Recount the baseline** from the deduplicated corpus: the Bash, PowerShell and file tool counts, the error
   classes, the heredoc failures by size, and the labels. Where a baseline script measured something the corpus
   cannot, such as the scratchpad scripts, rerun that script with the same deduplication.
4. **Restate the numbers** in `context.md` (the Baseline section and task 09's corpus paragraph), the README's
   "What it fixes" table, and each open task's Why table, each with the date of the recount. Say in `context.md`
   that the numbers before that date counted copies.

## Where

`plugins/io-guard/scripts/ioguard/cli/corpus.py`, `tests/cli/test_corpus.py`, `.claude/tasks/context.md`,
`README.md`, the open task files.

## Done when

- The corpus holds one record per tool use id, and its index says how many copies it skipped.
- Every baseline number the README and `context.md` state is a count of distinct calls, dated.
- Task 31 measures against the recounted baseline. It is numbered before this task, so it cannot depend on it:
  it names this task in its notes instead.

## What changed

The lead asked for this fixed at once, during task 13, because the doubled numbers would confuse.

- **`cli/corpus.py`:** `build` keeps the first record of each tool use id across every source, and skips the
  rest. `index.json` counts them as `copies`, and the corpus command prints the count.
- **Test, 320 in all, up from 319:** `test_a_call_held_by_several_transcripts_enters_once` builds a corpus from a
  call written twice in one file and once in another, and gets one record and 2 copies.
- **The recount** reads the rebuilt corpus with the baseline's own rules: its labels, and `baseline/tx_verbs.py`
  for what Bash was used for. The scratchpad counts come from the files on disk and stay as they were.
- **Restated:** `context.md`'s Baseline section, with a paragraph on why the numbers changed, the README's "What it
  fixes" table and its opening line, and tasks 13, 14, 16, 17, 20, 22, 24, 25, 26, 31 and 35. Task 31 now counts
  each tool use id once too. Task 35's issue comment also had the halving rule wrong, and now states row 25's.
- **Docs:** `docs/design/architecture.md` section 11. The drawing and `CLAUDE.md` need nothing.
- **Not restated:** the done tasks' records and D25's evidence, which are dated history. Tasks 11 and 12 counted
  copies. Counted once, task 12's `shell.writes` refuses 200 of 60,622 shell calls that ran, 0.33%, and warns on
  29. Task 11's `transport.body` moves 383 calls that ran and 202 that failed, and refuses 1.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- **The rebuilt corpus:** 110,379 records, and 70,099 copies skipped, from the same six folders that gave 180,478
  records an hour earlier. 5 calls had no result, and 0 lines were not JSON.
- **The largest changes:** `sed -i` 907 to 385, redirects into a source file 5,114 to 2,381, unexpected EOF 236
  to 125, the transport's failed commands 241 to 122, cwd resets 5,669 to 3,064, git LF warnings 432 to 328. The
  anchor misses moved least, 71 to 67. Not-read-yet stayed at 82.
- **Replay of the rebuilt corpus:** 110,379 records in 52.6 s, with no check raising.
- `python -m unittest discover -s tests -t .` ran 320 tests, all passing.

Not checked:

- **Which copy is kept.** The first file in path order wins. No copy was compared field by field with the one
  kept, so a copy whose result differs, if any does, is dropped unseen.
