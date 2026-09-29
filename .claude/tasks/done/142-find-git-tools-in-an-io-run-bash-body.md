---
title: A bash body run by io.run finds none of Git's own tools
stage: F
area: mcp
created: 2026-09-29
status: done
depends-on: []
findings: []
platforms: [windows]
commit: "fix: a bash body under io.run finds Git's own tools"
---

## Why

Raised from SmartTablesHost on 2026-09-29, in a live session. An `io.run` call with `lang: bash` ran its body
under Git's bash, and every coreutils program the body named was missing. The same commands work in Claude
Code's own Bash tool on the same machine in the same session, so a body moved from Bash to `io.run` breaks.

The call:

```json
{"lang": "bash", "code": "cd /c/Users/felia/Desktop/projs/unreal/SmartTablesHost\nF=Source/SmartTablesDemo/Private/SmartTableShowcaseModels.cpp\nclang-format --style=file \"$F\" | tr -d '\\r' > /tmp/fmt2.cpp\ndiff <(tr -d '\\r' < \"$F\") /tmp/fmt2.cpp && echo FORMAT-CLEAN\npython .claude/tools/shared/comment-audit.py --changed -v 2>&1 | tail -4\n", "timeout_s": 120}
```

What came back, exit 127:

```
"command": "'C:\\Program Files\\Git\\usr\\bin\\bash.EXE' C:\\Users\\felia\\.claude\\io-guard\\runs\\e0ae6b4fe1424d4ba07d24075362ddb4\\body.sh"
body.sh: line 3: tr: command not found
body.sh: line 4: tr: command not found
body.sh: line 4: diff: command not found
body.sh: line 5: tail: command not found
```

`clang-format` and `python`, which sit on the Windows PATH, were found. `tr`, `diff` and `tail` live in
`C:\Program Files\Git\usr\bin`, beside the `bash.EXE` that ran, and were not.

The likely cause: `usr\bin\bash.exe` started directly, not as a login shell and not through Git's
`bin\bash.exe` wrapper, keeps the Windows PATH as it is. Nothing puts `/usr/bin` or `/mingw64/bin` on it. Claude
Code's Bash tool starts bash so that both are on PATH. That is unchecked: read `lib/runs.py` `interpreter()`
and how the tool builds the environment before trusting it.

## What to build

A bash body under `io.run` sees the same programs a Bash tool call sees. Two routes, pick after reading how
Claude Code's Bash tool starts bash:

1. When the interpreter is Git's bash on Windows, put its own `usr/bin` and `mingw64/bin` at the front of the
   run's PATH, leaving every other entry in its order.
2. Start Git's `bin\bash.exe`, the wrapper that sets PATH up, instead of `usr\bin\bash.exe`. Check it keeps
   the call's `cwd`, since a login shell moves to HOME unless `CHERE_INVOKING` is set.

`argv` runs that name `bash` directly need the same answer, since they reach the same executable.

## Where

- `plugins/io-guard/scripts/ioguard/lib/runs.py`, `interpreter()`, where `lang: bash` picks the executable
- wherever `io.run` builds the child's environment, in `plugins/io-guard/scripts/ioguard/mcp/tools_run.py`
  or `lib/proc.py`

## Done when

- A test runs a bash body under `io.run` that calls `tr`, `diff`, `tail`, `sed` and `grep`, and each is found.
- The same body still runs in the folder `cwd` names.
- The call above, run live on Windows, prints `FORMAT-CLEAN` or a diff instead of `command not found`.

## Notes

- Found while checking a C++ file's formatting. The same check ran fine through `lang: python` straight after.
- macOS has coreutils on PATH already, so this is Windows only unless the fix touches shared code.

## What changed

- The cause, confirmed: this session's Bash tool runs Git's bash with `/mingw64/bin`, `/usr/local/bin` and
  `/usr/bin` first on PATH and `MSYSTEM=MINGW64`, as Git's login profile sets them. `io.run` started
  `usr\bin\bash.exe` straight, with the io server's Windows PATH, which holds none of Git's folders.
- Route 1 was built, with no login shell: a login shell reads the user's own profile files and moves to HOME.
  `lib/runs.py`: `git_tools(program)` gives `<git>/mingw64/bin`, `<git>/usr/local/bin` and `<git>/usr/bin` for
  a bash at `<git>/usr/bin/bash.exe` or `<git>/bin/bash.exe`, and nothing for any other program, WSL's
  `System32\bash.exe` included. `with_git_tools(env, program)` puts them first on PATH, whatever case its key
  is spelled in, and sets `MSYSTEM=MINGW64` unless the environment names one.
- `mcp/tools_run.py`: on Windows, `run` finds the program the argv starts, a `lang: bash` body's interpreter
  or a bash an argv names, and gives its run that environment.
- `tests/support/shells.py`: `git_folder` handles a git found at `<git>/mingw64/bin/git.exe`, which is where
  Git Bash's own PATH finds it. Before, it gave `<git>/mingw64` as the install folder.
- Tests, each failing first: `git_tools` for both bash paths and three other programs, and `with_git_tools`
  on a `Path` key, a kept `MSYSTEM` and another program (`tests/lib/test_runs.py`); a `lang: bash` body with
  Git's folders taken off PATH runs `tr`, `diff`, `tail`, `sed` and `grep`, prints `b`, `SAME`, `2`, `t` and
  `1`, and `pwd -W` gives the call's folder, where before each tool was `command not found`; an argv
  starting Git's bash runs `sed` (`tests/mcp/test_tools_run.py`). The suite of 1,059 passes on Windows, 2
  skipped.
- The failing call itself, through `io.run`'s code from this checkout with Git's folders off PATH, in
  SmartTablesHost, without its `comment-audit.py` line: exit 0 and `FORMAT-CLEAN`.
- `live-run-body` passed on the CLI 2.1.283.
- Docs: `docs/design/architecture.md` (how io.run starts a program, `runs.git_tools`, `runs.with_git_tools`).
- Checked on Windows on 2026-09-29.
