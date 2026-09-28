---
title: Blame an interpreter's script only for a write no other part of the command made
stage: I
area: checks
created: 2026-09-28
status: done
claimed-by: Pala Elektroniczna, session 7eeb509f
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

## What changed

The first plan, to leave out every file a redirect, `sed -i`, `tee`, `cp` or `mv` names, would never run:
`shell.writes` refuses each of those onto a tracked file before the command runs, so `scripted` never sees
them. Git is what gets through, so the rule is about git.

- `checks/touched.py`: `git_changes(simple, cwd, ctx)` gives the files one git command can change in the
  working tree:
  - `git mv`, `git restore`, and `git checkout -- <paths>`: the paths they name, resolved from the folder the
    command runs in, after any `cd`. A file at or under one of them is git's, and the script isn't named for it.
  - `git checkout` with no `--`, `git stash` other than `list` and `show`, `git reset --hard`, `--merge` or
    `--keep`, `am`, `apply`, `cherry-pick`, `merge`, `pull`, `rebase`, `revert` and `switch`: any file, so no
    script is named. A path git names through a variable counts as any file too.
  - Everything else, `git add`, `git rm` (it only deletes, and a deletion gets no `SHELL_WRITE`), a plain
    `git reset`: no file.
  `scripted` warns only for the tracked changed files that are left. It reuses `located` and `resolve` from
  `shell.writes` and `subcommand` from `lib.commit_message`.
- Tests: `tests/checks/test_touched.py` (1, twelve commands: which ones still name the script).
- Docs: none needed. The README's row says scripts are warned about, which still holds.

Evidence:

- `python tests/run_all.py` from Git Bash ran 863 tests, all passing, up from 862.
- The corpus: 58,779 Bash calls, 18,966 of them running a script file. With the new rule, 8 of those name no
  script (`git stash` 4, `git checkout` of a branch or a variable 3, `git apply` 1), and 25 leave git's named
  files to git (`git checkout --` 20, `git mv` 5). `tools/replay.py` cannot show the warning itself, since it
  needs the files a command changed, so a scratch script counted the calls the rule reaches.
- Today's two wrong warnings, `git mv .claude/tasks/open/6x-... .claude/tasks/done/ && ... python
  plugins/io-guard/scripts/precommit.py`, name the file under `.claude/tasks/done/`, which the `git mv` names.
  The twelve-command test holds the same shape.
- `live-script-write` passed on 2.1.283 on Windows on 2026-09-28: a script's own write to a tracked file still
  gets `SHELL_WRITE`.
