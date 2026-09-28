---
title: Measure the result against the baseline
stage: G
area: release
created: 2026-09-27
status: open
depends-on: [09, 28, 30]
findings: []
platforms: [windows]
commit: "test: measure failure classes before and after io-guard"
---

## Why

This is the acceptance test for the whole plugin. Once the guard is on, the baseline counts in `context.md` must
drop in the transcripts recorded from then on. The numbers also decide what comes next: hunk staging (task 32) and
the dashboard (task 33) wait for them (D20).

## What to build

`tools/measure.py`, generalised from `baseline/tx_scan.py`, `baseline/tx_eof.py` and `baseline/tx_verbs.py`. It
takes any set of project transcript folders and a date range. It uses the same classes and the same counting
rules as the baseline, so the two sets of numbers compare. It counts each tool use id once, as the corpus does
since task 37, because a resumed session copies its history into a new transcript. It reuses task 09's report format, and it reads the
telemetry through task 28's report for the guard's own side.

## Where

`tools/measure.py`.

## Done when

`tools/measure.py` can be built early. The measurement itself runs two weeks after task 30 turns io-guard on in the
four projects. Counted per 1,000 calls:

| Measure | Target | Baseline |
|---|---|---|
| Bash commands failing in transport | 0 | 122 |
| Edit anchor misses | At least 50% lower | 67 |
| Not-read-yet and modified-since-read errors | At least 50% lower | 82 and 30 |
| Git "LF will be replaced by CRLF" warnings on files the agents wrote | 0 | 328 |
| New scratchpad scripts that write files | At least 80% lower | 417 |
| Hook latency p95 | Within the 300 ms budget (D16) | Not measured |

## Blocked on

Two weeks of sessions with io-guard on. Task 30 turned it on in the four projects on 2026-09-28, so the
measurement runs on or after 2026-10-12:

```
python tools/measure.py CLICKER=<its transcript folders> OrbitalDrift=... SmartTablesHost=... UNREAL-SHARED=...
```

## What changed so far

- **`tools/measure.py`**, the cli's `measure` command in `ioguard/cli/measure.py`. It reads the transcript
  folders through `corpus.records`, now shared with the corpus build, so each tool use id counts once, and
  splits the calls at `--since`, 2026-09-28 by default. Each measure comes from the corpus labels task 09 set:
  `unexpected-eof` and `heredoc-eof` for transport, `not-found`, `not-read-yet`, `modified-since-read` and
  `git-eol`, and a Write of a scratchpad script whose text writes a file, counted once per path. The hook p95
  comes from the telemetry through task 28's report, whose percentiles now include p95. A period after of
  fewer than 1,000 calls gives no verdict.
- **The before side reproduces the baseline.** 110,424 calls from 2026-05-29 to 2026-09-27, against the
  baseline's 110,379, give per 1,000: transport 1.14 (126, baseline 122), anchor misses 0.61 (67), not read
  yet 0.74 (82), modified since read 0.28 (31, baseline 30), git LF and CRLF 2.97 (328). Scratchpad scripts
  that write files come to 11.66 (1,287 paths), where the baseline counted the 417 files still on disk, so
  that row compares the two periods only, never the old number. On 2026-09-28 the hook p95 was 82.5 ms.
- Tests: `tests/cli/test_measure.py` 4.
