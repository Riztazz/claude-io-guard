---
title: Build the offline check command the docs name, or take the claim out
stage: I
area: cli
created: 2026-09-28
status: open
depends-on: [07]
findings: []
platforms: [windows, macos]
commit: "feat: run the checks on one command or one file, offline"
---

## Why

`CLAUDE.md` says "The checks on one command, offline: `python tools/ioguard.py check "<command>"`", and the
`io-guard-dev` skill's lookup table names `python tools/ioguard.py check "<command>"` and
`python tools/ioguard.py profile <file>`. On 2026-09-28 neither exists: `tools/` holds `corpus.py`,
`measure.py`, `replay.py`, `report.py`, `skill.py` and `probes/`, and `cli/main.py` has no `check` or `profile`
command. A reader who follows either doc gets "No such file or directory".

## What to build

- `check "<command>"`: build a Bash PreToolUse event for the command in the current folder, run the pipeline
  with the live context from io-guard's folder, and print each decision, code and fix. It runs nothing.
- `profile <file>`: print the file's profile: encoding, BOM, line endings, indent, final newline.
- `tools/ioguard.py`, holding no logic, as the other `tools/` scripts do.
- Or, if the lead decides the commands aren't wanted, take the lines out of `CLAUDE.md` and the skill.

## Where

`plugins/io-guard/scripts/ioguard/cli/main.py`, `tools/ioguard.py`, `tests/cli/test_main.py`, `CLAUDE.md`,
`.claude/skills/io-guard-dev/SKILL.md`.

## Done when

- Both lines in the docs run as written, or are gone.
