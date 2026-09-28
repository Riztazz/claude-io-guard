---
title: Build the offline check command the docs name, or take the claim out
stage: I
area: cli
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
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

## What changed

- `cli/check.py`, new:
  - `check(command, cwd, env, tool)` builds the PreToolUse event a Bash or PowerShell call from `cwd` would send.
    It runs the whole pipeline with the live config and probe of `project_root(cwd)` and io-guard's folder.
  - `DryFs` is the live file system with every write kept in memory. A body `transport.body` moves is never
    written, and a later check reads it from memory. The session state and the telemetry stay in memory too.
  - `render(outcome)` prints the verdict, then each check that said something, with its lines as the model
    would get them, and the command as it would run after a rewrite.
  - `profiled(path)` prints the profile line a Read gets.
- `cli/main.py`: `check COMMAND [--tool Bash|PowerShell] [--cwd FOLDER]`, which exits 1 on a refusal, and
  `profile FILE [FILE ...]`. Each names a missing folder or file and exits 1.
- `tools/ioguard.py`: the whole command line, `main(sys.argv[1:])`, with no logic.
- Tests: `tests/cli/test_main.py` (5: a `sed -i` on a tracked file is refused and the file is untouched, a
  heredoc over a 6,000-byte budget is moved with no file written in the project or io-guard's folder, a missing
  `--cwd`, a CRLF BOM file's profile, a missing file).
- Docs: `CLAUDE.md` (the layout's list of cli commands), `docs/design/architecture.md` (the package tree).
  The `CLAUDE.md` running line and the skill's two lines already matched the commands as built.

Evidence:

- `python tests/run_all.py` ran 858 tests, all passing, up from 853.
- Live on Windows on 2026-09-28, from this checkout:
  - `check "sed -i 's/a/b/' CLAUDE.md"` printed `SHELL_WRITE` under `shell.writes: deny` and exited 1.
  - `check` of a 12,515-byte heredoc printed `BODY_MOVED_TO_FILE` and the command reading
    `~/.claude/io-guard/bodies/body-4d4bcc9bdc15aa33.txt`. That file does not exist, and io-guard's folder
    held 83 files before and after.
  - `check "ls -la | head"` and `check "cat foo.txt" --tool PowerShell` printed `Verdict: observe` and exited 0.
  - `profile CLAUDE.md` printed `CLAUDE.md: LF, UTF-8, 2 spaces, 122 lines`.
- From PowerShell, 10 tests in `tests/hooks/test_launcher.py` and `tests/lib/test_shell.py` fail, since
  `bash` there is WSL's launcher. Neither file touches this task's code. Task 59 has it.
- `tools/ioguard.py` joins task 47's table, since it answers `--help` through `cli/main.py`.
