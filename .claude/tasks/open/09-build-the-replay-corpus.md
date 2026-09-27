---
title: Build the replay corpus and harness from local transcripts
stage: A
area: infra
created: 2026-09-27
status: open
depends-on: [07]
findings: [SHW-8, GRD-1]
platforms: [windows]
commit: "test: replay recorded tool calls through every check, offline"
---

## Why

A guard that refuses harmless commands teaches agents to route around it. The kit's current guard refused
`git commit -m @'...'@ 2>&1 | Select-Object -Last 6` a day after it shipped, because it read `2>&1` as a file
redirect (SHW-8). The recorded calls are the best test set there is: 97,579 Bash commands, 26,098 Edit calls and
10,920 Write calls, each with its result. The same harness measures what each check would have caught.

## What to build

- **`tools/corpus.py`.** Read transcript folders given on the command line (`~/.claude/projects/<project>/`),
  pair each tool call with its result, and write a JSONL corpus to `corpus/`: the tool, the input, a result
  excerpt, `is_error`, and a failure label from the rules in `baseline/tx_scan.py`. `corpus/` is gitignored and
  never leaves the machine (D8).
- **`tools/replay.py`.** Run every registered check over the corpus through the pipeline, without executing
  anything. Report, per check: would fix, would refuse, would warn, each split by whether the recorded call
  succeeded or failed. A refusal of a call that succeeded is a false-positive candidate, and the report samples 20
  of them for review.
- **Seed labels** from the baseline: the 236 unexpected-EOF commands, the 71 anchor misses, the 12 guard
  refusals and the 37 MSYS conversions.

## Where

`tools/corpus.py`, `tools/replay.py`, `corpus/` (local only).

## Done when

- The corpus builds from the four projects' transcripts on this machine.
- Replay over the whole corpus takes under 10 minutes.
- The report format is fixed, and task 31 reuses it.

## Notes

- Start from `baseline/tx_scan.py`, `baseline/tx_eof.py` and `baseline/tx_verbs.py`. Their paths are hard-coded
  to this machine.
