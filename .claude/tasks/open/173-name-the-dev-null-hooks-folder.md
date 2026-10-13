---
title: Name the dev/null folder of Git LFS hooks, and the hooksPath=/dev/null that writes it
stage: H
area: runtime
created: 2026-10-05
status: open
depends-on: []
findings: []
platforms: [windows]
commit: "feat: name a dev/null hooks folder and the hooksPath that writes it"
---

## Why

CLICKER's repository grew an untracked `dev/null/` folder holding Git LFS's four stock hooks, `pre-push`,
`post-checkout`, `post-commit` and `post-merge`: on 2026-10-04 at 14:42:06, and again on 2026-10-05 at 10:07:41
after the lead had it deleted. io-guard never saw the call that wrote it, because no tool call wrote it.

The writer is the `security-guidance` plugin from `claude-plugins-official`, here installed through the Claude desktop
app (`%APPDATA%/Claude/local-agent-mode-sessions/.../rpm/plugin_01MsZoTpmgRVtWrC5gZtXVza/hooks/`). Its
`hooks/gitutil.py` runs every git command as

    GIT_CMD = ["git", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null", "-c", "core.quotePath=false"]

from Python, with no shell, and its `UserPromptSubmit` hook runs `git stash create` on every prompt, a background
task's notification included. The plugin's log (`~/.claude/security/log.txt`) has `Processing:
hook_event=UserPromptSubmit` at 10:07:40.311 and `Captured git baseline: df8efac9d4ca` at 10:07:41.501, and
`dev/null/` was written at 10:07:41.28, between the two.

With a changed LFS-tracked file in the tree, `git stash create` runs Git LFS's clean filter, and Git LFS 3.6.1
installs any missing hook into `core.hooksPath`. On Windows it reads `/dev/null`, which has no drive letter, as a path
relative to the work tree, so the hooks land in `<repo>/dev/null/`. Git Bash hides this: it rewrites `/dev/null` in
the `-c` argument before git sees it, so the same command typed into the Bash tool writes nothing.

Reproduced in a throwaway repository on 2026-10-05 (git-lfs/3.6.1, Git for Windows):

    git init; git lfs track "*.uasset"; commit a.uasset; delete .git/hooks/{pre-push,post-checkout,post-commit,post-merge}
    change a.uasset
    from Python: subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "stash", "create"], cwd=repo)
    -> dev/null holds post-checkout, post-commit, post-merge, pre-push; .git/hooks holds none

Without the `-c`, the same `git stash create` puts the four hooks back into `.git/hooks`.

## What to build

1. **A check on a command io-guard sees** (Bash, PowerShell and `io.run`): on Windows, a `core.hooksPath=/dev/null`,
   in a `-c` or a `GIT_CONFIG_*` variable, is named with the folder it would grow when Git LFS runs, and the fix
   names an empty folder outside the repository instead. A command from Git Bash is safe today only because of the
   path rewriting, so the note says that too.
2. **A session-start or post-run note** when a repository io-guard works in holds an untracked `dev/null/` whose files
   are Git LFS's stock hooks: name it, name the cause above, and say it is safe to delete and comes back while the
   writer runs.
3. **The upstream report**, as task 35 does for the Bash transport bug: the plugin's `GIT_CMD` on Windows, with the
   reproduction above. `os.devnull` gives `nul`, which Git LFS would read as a relative path too, so the safe value
   is an empty folder outside the work tree.

## Where

- io-guard's command checks: `plugins/io-guard/scripts/ioguard/checks/` beside `win_paths.py`, which already rewrites
  `>nul` to `/dev/null` for Git Bash (PTH-5).
- The session probe: `plugins/io-guard/scripts/ioguard/checks/session_probe.py`.
- The plugin, upstream: `claude-plugins-official/plugins/security-guidance/hooks/gitutil.py`, `GIT_CMD` near line 25,
  and `security_reminder_hook.py`'s `UserPromptSubmit` handler, near line 514.

## Done when

- A Bash, PowerShell or `io.run` command on Windows carrying `core.hooksPath=/dev/null` gets the note and the fix,
  with a test for each shell.
- A repository holding an untracked `dev/null/` of Git LFS hooks gets the note once, with a test.
- The upstream report is filed, or written up for the lead to file.

## Notes

- No catalog id fits yet. It is close to PTH-5, the `nul` file Git Bash writes, with the same root: a Unix device path
  meeting a Windows program.
- Raised from CLICKER on 2026-10-05. The lead asked whether a Bash command did it and io-guard missed it. It was not a
  tool call: a plugin hook's Python subprocess, which no PreToolUse or PostToolUse hook sees.
