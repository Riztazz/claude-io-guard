---
title: See the shell writes shell.writes misses
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: [97]
findings: [SHW-1]
platforms: [windows, macos]
commit: "fix: shell.writes sees the in-place and redirect writes it missed"
---

## Why

The code review of 2026-09-29: slice A items 12, 13 and 14, slice B item 3. Each command below writes the
tracked `README.md` and was let through, verdict OBSERVE, by `tools/ioguard.py check` on Windows on 2026-09-29,
where `sed -i s/a/b/ README.md` and `echo x > README.md` are refused with `SHELL_WRITE`:

| Command | Why it was missed |
|---|---|
| `perl -0pi -e 's/a/b/' README.md` | `^-[a-zA-Z]*i` fails on the digit |
| `gsed -i s/a/b/ README.md` | `gsed` is not a known writer, and macOS users run it |
| `find . -name README.md -exec sed -i s/a/b/ {} +` | the writer is an argument of `find` |
| `(cd docs && ls); sed -i 's/a/b/' README.md` | the subshell's `cd` leaks, so the path resolves under `docs/`. `pushd docs; popd` does the same |
| `bash -c 'echo x > README.md'` | the inner string is not read, though `io.run` reads it since D41 |
| `echo x >| README.md` | `>>?\|>\|` matches `>` first |
| `echo x >& README.md`, `echo x > $'README.md'` | read as a stream copy, and `$` kept |
| PowerShell `Set-Content -Path:README.md -Value x`, `Clear-Content README.md` | `named()` wants a bare `-Path` word |
| PowerShell `echo hi>README.md` | a redirect needs a space before `>` |

The reviewers also name `xargs sed -i`, `sed -i ... *.md`, `env X=1 sed -i`, `sed -I`, `ruby -pi`,
`awk -i inplace`, `node -e "writeFileSync"`, PowerShell `New-Item -Value`, and
`[IO.File]::WriteAllText((Resolve-Path f), ...)`.

## What to build

- Each row above refused with `SHELL_WRITE`, through the scanner task 97 fixes. A wrapped `bash -c` string is
  read with `rules.inner`. `cd` in a subshell and `pushd` and `popd` keep their scope.
- A replay over the corpus before shipping: the false refusal rate of `shell.writes` stays under 0.1%, and each
  refusal of a call that succeeded is read.
- Folded in from task 122 on 2026-09-29: `shell_writes.py` calls `script_files` twice for each Bash command,
  once in the refusal and once for `shell.touched.scripted`, so each script is read twice. Read it once.

## Where

`checks/shell_writes.py`, `lib/shell.py`, `lib/pwsh.py`.

## Done when

- Every row is refused, the replay numbers are in `## What changed`, and the existing tests pass.

## What changed

- `lib/shell.py`: `REDIRECT` tries `>|` before `>`, and `>&file` is a redirect of both streams to the file,
  where `>&1`, `>&2` and `>&-` stay stream copies. `unquote` drops the `$` of `$'...'` and `$"..."`.
  `subshells` gives the `( )` group of each offset and each group's parent, `$(` and `((` opening none.
- `checks/shell_writes.py`:
  - `in_place` names the in-place editors: sed and gsed with `-i`, `-I` or `--in-place`, perl and ruby with
    any flag group holding `i` (`-0pi`), awk and gawk with `-i inplace`. `code_files` gives perl's and
    ruby's files.
  - `without_env` drops a leading `env` and its settings, and `rules.unwrapped` the other wrappers.
  - `delegated` reads a writer that `find -exec` or `xargs` runs, and its target is `find`'s folders, or `.`
    for `xargs`, which git answers for as a folder that holds tracked files.
  - A `bash -c` or `pwsh -Command` string is read through `rules.wrapped`, up to `rules.NESTED` deep, and a
    code string such as `node -e` is read for the files it opens, from the folder its own command runs in.
  - `targets` matches a `*` or `?` in a target's last name against its folder.
  - `located` keeps a cd inside `( )` in its subshell, and `popd` goes back to where `pushd` left.
  - PowerShell: `named` reads `-Path:value`, `Clear-Content` and `clc` write, `New-Item` and `ni` write with
    `-Value` or `-Force`, and a redirect needs no space before it (`lib/pwsh.py`, which also reads
    `(Resolve-Path x)`, `Convert-Path` and `Get-Item` inside an `[IO.File]` call).
  - Folded from task 122: `run` reads the script files once and hands them to `bash_writes`.
  - The refusal of any `-i` editor names `io.edit`.
- `checks/touched.py`: calls `located` with the command and its scan.
- Tests: each row of `## Why` and the three `find` and `xargs` forms refused, a folder with no tracked file
  left alone, a cd in a subshell kept there, five PowerShell forms, and a code string resolved from its own
  folder. All 20 row cases failed before the change. The suite is 996, all passing on Windows.
- Replay, `shell.writes` alone over every recorded Bash and PowerShell call, HEAD against the change, per
  record: one verdict changed. `cd OrbitalDrift && python -c "...open('Source/.../NavPanelCullTests.cpp',
  'wb').write(...)"`, a call that ran and rewrote a tracked file, is now refused: HEAD resolved the body from
  the folder of an earlier `python editor.py`. No refusal was added to a call that wrote no tracked file, so
  the false refusal rate did not move. A first cut of the change got five scratchpad `python -c` bodies
  wrong and lost one refusal, all from one cause, the code-string branch taking `python -c` before the
  interpreter's folder was set. The replay showed it, a test holds it, and the second replay shows it gone.
  The whole-pipeline replay counted 211 refusals of calls that ran before and 210 after the first cut. Its
  samples are 20 a check, so the per-record replay above is the one to read.
- Docs: `docs/design/architecture.md` (the `shell` and `pwsh` signatures and the package tree), the
  `shell_writes.py` docstring.
- Checked on Windows on 2026-09-29. Not checked live: the unit tests run the real reader on each form, and
  the replay ran it over 62,100 recorded calls.
