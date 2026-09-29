---
title: See the shell writes shell.writes misses
stage: I
area: checks
created: 2026-09-29
status: open
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
