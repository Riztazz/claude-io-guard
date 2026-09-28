---
title: Give every io-guard script a --help, and keep it so with a test
stage: I
area: cli
created: 2026-09-28
status: open
depends-on: [28]
findings: []
platforms: [windows, macos]
commit: "feat: every script answers --help without doing anything else"
---

## Why

An agent that meets a script it does not know runs it with `--help`, and reads the source when nothing comes
back. The lead saw an agent do that on 2026-09-28 with the kit's comment audit, and asked for help on
everything, "so bots can scan and not parse". The kit's scripts are a kit ticket,
`UNREAL-SHARED/tasks/open/give-every-kit-script-a-help.md`. This task is io-guard's own.

Checked the same day with `--help` on each:

| Script | Today |
|---|---|
| `tools/corpus.py`, `replay.py`, `report.py`, `measure.py`, `ioguard.py` | argparse usage, through `cli/main.py` |
| `plugins/io-guard/scripts/precommit.py` | argparse usage |
| `tools/probes/run_probe.py` | prints its module docstring |
| `tools/skill.py` | prints nothing |
| `plugins/io-guard/scripts/hook.py`, `server.py` | not run: each reads stdin, so `--help` in a terminal waits |

## What to build

- **`tools/skill.py --help`** prints its usage and `--check`, and writes nothing.
- **`hook.py --help` and `server.py --help`** say what starts them and how, and exit 0 without reading stdin.
- **`run_probe.py --help`** keeps its docstring, and exits 0.
- **`pyrun`** passes its arguments to Python, so `pyrun --help` is Python's. `docs/launcher.md` says so.
- **A meta test** runs every script under `tools/` and `plugins/io-guard/scripts/`, with `--help` and no stdin,
  and fails on a nonzero exit, on empty output, on a run past 10 seconds, or on a file the run changed.
- **The `io-guard-dev` skill** states the rule beside "Every state worth checking is one command away".

## Where

`tools/skill.py`, `plugins/io-guard/scripts/hook.py`, `plugins/io-guard/scripts/server.py`,
`tools/probes/run_probe.py`, `tests/test_meta.py`, `.claude/skills/io-guard-dev/SKILL.md`, `docs/launcher.md`.

## Done when

- Every script answers `--help` with its usage and exits 0 at once, and the meta test holds it there.
