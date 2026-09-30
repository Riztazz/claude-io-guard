---
title: io.run with argv cannot start grep, which the session's Bash tool runs
stage: I
area: mcp
created: 2026-09-30
status: done
depends-on: []
findings: [SHL-3]
platforms: [windows, macos]
commit: "fix: io.run finds a program where the Bash tool finds it"
---

## Why

Raised from SmartTablesHost on 2026-09-30, in a live session on Windows 10 with Git for Windows installed. The
lead asked for every read, write and run to go through io-guard. The first `io.run` of a plain Unix tool failed
where the Bash tool runs the same tool every day.

The call:

```
io.run  argv: ["grep", "-n", "^def \\|^    \"\"\"", ".claude/release/marketing/shoot_editor.py"]
        cwd:  C:\Users\felia\Desktop\projs\unreal\SmartTablesHost
```

The answer:

```
PATH_NOT_FOUND: io.run could not start grep: grep is not on PATH, so io-guard did not start it.. Name the program by its full path, or check that it is installed.
```

A python body run through `io.run` on the same machine, a minute later, printed:

```
PATH has git usr/bin: False
shutil.which grep: None
C:\Program Files\Git\usr\bin\grep.exe True
C:\Program Files\Git\bin\bash.exe True
```

So grep is installed, and the environment io.run hands its programs lacks Git for Windows' `usr\bin`, which the
Bash tool's shell has. An agent moving a command from Bash to `io.run` loses grep, sed, awk, find, head and the
rest, and the message sends it off to check an install that is fine. The cause of the missing PATH entry is not
checked in the code.

The message also ends its first sentence with two dots: `did not start it..`.

## What to build

- `io.run` with argv resolves a program the session's Bash would find. One way: when the name is not on PATH and
  Git for Windows is installed, look in its `usr\bin` and `mingw64\bin` too, and say in the result where it found
  the program.
- When it still finds nothing, the message names the folders it looked in.
- The double dot goes.

## Where

The argv start path of `io.run` and the text of its `PATH_NOT_FOUND` refusal. Not located in the code yet.

## Done when

- `io.run` with `argv: ["grep", "--version"]` on a Windows machine with Git for Windows prints grep's version.
- A test covers a program found only under Git's `usr\bin`.
- The refusal text has one dot at the end of each sentence.

## What changed

Numbered 149 when it was picked up on 2026-09-30.

The report reproduced word for word: `io.run` with `argv: ["grep", "--version"]` in this session answered
`PATH_NOT_FOUND: io.run could not start grep: grep is not on PATH, so io-guard did not start it..`. The cause,
which the report had not found in the code: `mcp/tools_run.py` put Git's tool folders on PATH only when the
program was Git's bash itself (task 142), and `proc.located` looked for any other name on the Windows PATH
alone, which holds `System32` and `Git\cmd` and none of Git's tools. The double dot came from `tools_run.py`
adding a period to `proc.not_on_path`'s sentence, which already ends in one.

At the lead's request, Fable reviewed the fix before it landed, since finding a program on Windows keeps coming
back. It found seven holes. Five are fixed here, each checked on this machine before the change:

1. **Windows' own program won over Git's.** With PATH first, `find`, `sort` and `bash` started `System32`'s
   `FIND`, `SORT` and WSL's `bash.exe`: `io.run` of `find --version` answered `FIND: Parameter format not
   correct`. `runs.start` now looks for a bare name in the Bash tool's bash's tool folders before PATH, as
   that shell does.
2. **A regression in the first draft of this fix.** `runs.start` put Git's folders on PATH on every
   platform, and `git_tools` read `/usr/local/bin/bash` as Git's, so a macOS body's PATH began
   `\usr\local\mingw64\bin;...`. `git_tools` now answers only for a path with a drive.
3. **A body's bash with no probed bash was WSL's.** `runs.interpreter` now skips `System32` and
   `WindowsApps`, as the session probe does. `NOT_BASH` moved from `checks/session_probe.py` to `lib/runs.py`
   so both use one.
4. **A call's `Path` beside the session's `PATH`** reached the program as two variables. On Windows,
   `environment` now merges names without case.
5. **The message named folders that do not exist,** such as a Cygwin bash's `mingw64\bin`, and called any
   bash's folders "Git for Windows' tools". It now names only folders that exist, as the folders the Bash
   tool's shell adds.

Filed as task 151: git itself, the verify and format commands, and the first session's `probe.json`, the three
other places that start a program by bare name.

What `io.run` does now: a program named without a folder is looked for in the tool folders of the probe's
bash that exist, then on PATH. Found there, it runs by its full path, with those folders first on PATH and
`MSYSTEM` set, and the result's note says `io-guard ran grep as C:/Program Files/Git/usr/bin/grep.EXE, where
the Bash tool's shell finds it.` Found nowhere, the refusal is one sentence: `io.run could not start X: X is in
no folder on PATH, nor in the folders the Bash tool's shell adds, ..., so io-guard did not start it.`

The tests, each seen failing first:

- `tests/lib/test_runs.py`: a program only Git's folders hold starts by its full path, Git's `find` comes
  before `System32`'s, a program named by its path runs as named, macOS bash paths get no Git folders, and a
  body's bash skips `System32`. These run on macOS CI too, with temporary folders.
- `tests/mcp/test_tools_run.py`, on Windows with Git: `grep` runs from Git's `usr/bin` with its note, `find`
  is GNU find, and a refusal names no missing folder. On every platform: a missing program's refusal is one
  sentence with one final dot, and a call's `Path` replaces the session's `PATH`.

The live probe: `live-run-tools` in `tools/probes/run_probe.py` asks Haiku for `io.run` of `grep --version` and
`find --version`, and passes when both results show GNU's names. It passed on the CLI 2.1.283: `grep (GNU grep)
3.0` and `find (GNU findutils) 4.10.0`, exit 0, each with the note naming `C:/Program Files/Git/usr/bin`.
`live-run-body`, `live-run-asked`, `live-server`, `live-empty` and `live-format` passed beside it.

Evidence:

- `python tests/run_all.py`: 1,118 tests, OK, 2 skipped, against 1,110 at task 148.

Docs: `docs/design/architecture.md` has `runs.start` in the `runs.py` signatures and the lookup order in
`io.run`'s section. `docs/tools.md` says nothing about PATH.

Checked on Windows 10 on 2026-09-30. macOS is covered by CI only.
