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
rules as the baseline, so the two sets of numbers compare. It reuses task 09's report format, and it reads the
telemetry through task 28's report for the guard's own side.

## Where

`tools/measure.py`.

## Done when

`tools/measure.py` can be built early. The measurement itself runs two weeks after task 30 turns io-guard on in the
four projects. Counted per 1,000 calls:

| Measure | Target | Baseline |
|---|---|---|
| Bash commands failing in transport | 0 | 241 |
| Edit anchor misses | At least 50% lower | 71 |
| Not-read-yet and modified-since-read errors | At least 50% lower | 82 and 55 |
| Git "LF will be replaced by CRLF" warnings on files the agents wrote | 0 | 432 |
| New scratchpad scripts that write files | At least 80% lower | 417 |
| Hook latency p95 | Within the 300 ms budget (D16) | Not measured |
