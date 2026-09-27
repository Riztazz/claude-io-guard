---
title: Build the replay corpus and harness from local transcripts
stage: A
area: infra
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
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

## What changed

- **`plugins/io-guard/scripts/ioguard/cli/`**, the first of the command line, because `tools/` scripts hold no
  logic (`architecture.md`, section 1):
  - `labels.py`: the baseline's result rules, command shapes and file error classes, as data. The patterns
    for a BOM, a NUL and a backslash are built with `chr()`, so the file stays ASCII.
  - `corpus.py`: `Record`, `read_transcript`, `build` and `load`. A record keeps the whole input, the first
    2,000 characters of the result and its length, the structured `toolUseResult` cut at 4,000 characters and
    200 items, the permission mode of the last prompt, the version, the cwd and the labels.
  - `replay.py`: `Replay`, `replay` and `render`. Each record runs as PreToolUse, then PostToolUse or
    PostToolUseFailure, in an in-memory context per session with telemetry off. The report counts fix, refuse
    and warn per check, split by whether the call ran, with the labels it acted on and an even sample of 20
    refusals of calls that ran.
  - `main.py`: the `corpus` and `replay` commands.
- **`tools/corpus.py` and `tools/replay.py`** put the scripts folder on the path and call `main`.
- **The seed labels:** `unexpected-eof`, `not-found` for the anchor misses, `guard-refused` and `msys-path`.
  `guard-refused` now matches only the guard's refusal text, because the baseline's rule also matched the
  guard's file name in git status lines, diffs and listings.
- **Tests, 227 in all, up from 201:** `tests/cli/` covers the labels, the corpus on synthetic transcripts,
  replay with the test checks, and both `tools/` scripts as subprocesses. `tests/support/transcripts.py`
  builds the transcript lines, so no test reads the lead's transcripts.
- **Docs:** `docs/design/architecture.md` section 1 (the `cli` files) and section 11 (the corpus and the report's
  fixed shape), `context.md` (the corpus counts against the baseline), `CLAUDE.md` and the `io-guard-dev`
  skill. The drawing shows no command line, so it needed nothing.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- **The corpus:** `python tools/corpus.py` over the six transcript folders of the four projects wrote 180,464
  records in 1 min 23 s: CLICKER 116,523, OrbitalDrift 26,270, SmartTablesHost 25,664 and UNREAL-SHARED
  12,007. Five calls had no result, and no line failed to parse.
- **The seed labels against the baseline:** anchor misses 71 against 71. `unexpected-eof` 246, which is the
  baseline's 236 plus 10 from that morning's sessions, split by the records' dates. `msys-path` 39 against 37.
  `guard-refused` 14, 12 of them failed calls, against the baseline's 12.
- **Replay speed:** the whole corpus in 17.1 s with no check registered, and in 29.8 s with four test checks
  installed through `tests/support/inject`, 360,928 pipeline runs. The note check's warn count equalled every
  event, and the output check's equalled the 96,338 Bash calls that ran.
- `python tests/run_all.py` ran 227 tests, all passing.

Not checked:

- **A real check's false-refusal rate.** No check is registered yet, so the report's counts are zero. Each check
  task runs the replay before it ships.
- **Replay speed with real checks.** The test checks cost almost nothing. A check that reads files runs against
  an empty in-memory file system in replay, so its cost there is not its cost live.
