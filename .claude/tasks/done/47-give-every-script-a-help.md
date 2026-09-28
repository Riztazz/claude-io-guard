---
title: Give every io-guard script a --help, and keep it so with a test
stage: I
area: cli
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
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

## What changed

- `mcp/skill.py`: `main` parses its arguments with argparse, so `tools/skill.py --help` prints its usage and
  `--check`, and an unknown argument exits 2.
- `hook.py` and `server.py` print their docstring for `-h` or `--help` and exit 0, before `hook.py` reads stdin.
  `hook.py` keeps to 3.8 syntax.
- `tools/probes/run_probe.py`: `-h` and `--help` print the docstring and exit 0. Any other unknown command still
  prints it and exits 2.
- `tools/probes/plugin/scripts/probe_hook.py` and `probe_server.py` do the same before they read `probe.json`,
  and their docstrings say what starts them. The meta test's scan found them, so they're in.
- Tests: `tests/test_meta.py`, `EveryScriptAnswersHelp` (1). A script is a `.py` file under `tools/` or the
  plugin's `scripts/` that calls `sys.exit(main(` or checks `__main__`, which finds 12. Each runs with `--help`,
  no stdin and a 10-second limit. It passes on exit 0 with argparse's usage or the docstring's first line in
  stdout, and with no file in the checkout changed, ignored files included.
- Docs: `docs/launcher.md` (`pyrun --help` is Python's, and a script's own `--help`), the `io-guard-dev` skill
  (Layout, rule 4). No drawing, design or README change: no component, signature or setting moved.

Evidence:

- `python tests/run_all.py` from Git Bash ran 860 tests, all passing, up from 859.
- HEAD's `hook.py --help` printed `{}` and exited 0, and HEAD's `run_probe.py --help` exited 2. The meta test
  fails on both: `{}` is neither usage nor the docstring.
- `live-empty`, which runs the shipped `hook.py` and `server.py`, and `mcp-gate`, which runs `probe_server.py`,
  both passed on Claude Code 2.1.283 on Windows on 2026-09-28.
- `tools/skill.py --check` exits 0.
