---
title: Blame an interpreter's script only for a write no other part of the command made
stage: I
area: checks
created: 2026-09-28
status: open
depends-on: [48]
findings: []
platforms: [windows, macos]
commit: "fix: a script is named for a write only when nothing else in the command wrote"
---

## Why

On 2026-09-28 this repository's session ran one Bash command:

```
git mv .claude/tasks/open/61-... .claude/tasks/done/ && git add .claude/tasks/done/61-... ... &&
python plugins/io-guard/scripts/precommit.py; echo "precommit=$?"; git status --short
```

`git mv` moved the task file. `precommit.py` only reads. PostToolUse said:

```
SHELL_WRITE: plugins/io-guard/scripts/precommit.py changed
.claude/tasks/done/61-name-the-project-root-in-io-tool-telemetry.md, which git tracks, so those writes skipped
io-guard's byte checks and Claude Code's checkpoints. Make the next change to them with
mcp__plugin_io-guard_io__io_edit or the Edit tool.
```

`checks/touched.py`, `scripted`, blames the first script run for every tracked file the whole command changed.
It cannot tell which part of the command wrote, so the message names a writer it does not know.

## What to build

- Name the script only when no other simple command in the command is one `shell.writes` knows as a writer,
  such as `git mv`, `git checkout`, `cp`, `mv` or a redirection. Otherwise say nothing, since `TOUCHED_BY_SHELL`
  already names the files.
- Or word it as the command's write, with the script as one of the parts that ran. Pick one and say why here.
- A test for each: `git mv a b && python s.py` names no script, and `python s.py` alone still does.
- Replay the corpus, and give the warning's count before and after in `## What changed`.

## Where

`plugins/io-guard/scripts/ioguard/checks/touched.py`, `plugins/io-guard/scripts/ioguard/lib/shell.py`,
`tests/checks/test_touched.py`.

## Done when

- A compound command whose write came from a known writer gets no `SHELL_WRITE` naming a script.
