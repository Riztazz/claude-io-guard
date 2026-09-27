---
title: Refuse shell writes to tracked files, and port the kit's current guard
stage: B
area: transport
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [08, 09]
findings: [SHW-1, SHW-8, BYT-2, BYT-8, BYT-9, GIT-1, GRD-1]
platforms: [windows, macos]
commit: "feat: send file writes from the shell to the edit tools, with a fix in every refusal"
---

## Why

A write through the shell skips every byte check and the checkpoint rewind (SHW-1). The baseline counts:

| Route | Count |
|---|---|
| `sed -i` commands | 907 |
| Redirects into a source-type file | 5,114 |
| Set-Content, Out-File or WriteAll* calls | 196 |
| Scratchpad scripts that write files | 417 |

Auto mode tells agents to prefer these routes, so every refusal has to name the route that works.

The kit's current guard, `UNREAL-SHARED/tools/shell-write-guard.py`, runs in this repository while it is built
(task 00). It has two problems. It refused `git commit -m @'...'@ 2>&1 | ...` because it read `2>&1` as a file
redirect (SHW-8). It also refuses writes to scratch files, which cost nothing.

## What to build

A PreToolUse check on Bash and PowerShell:

1. **Detect writes:**
   - `sed -i` and `perl -i`
   - `>` and `>>` into a path, but not `2>&1`, `>&2`, `/dev/null`, `$null` or `nul`
   - `tee`
   - `Set-Content`, `Add-Content`, `Out-File` and `[IO.File]::Write*`
   - `cp`, `mv` or `Copy-Item` onto a tracked file
   - `open(..., 'w')`, `write_text` or `write_bytes` in an inline or moved body
   - `cat > out <<'EOF'` in both forms: as written, and as task 11 moves it when it is long,
     `cat > out < "<scratchpad>/io-guard/body-<hash>.txt"`. Task 11's check runs first, in the transport layer,
     and moves any quoted heredoc over the budget, whatever it feeds
2. **Tracked or not:** ask git once per path and cache the answer for the session. Writes to the scratchpad, and
   to paths outside any repository, pass.
3. **Refuse with `SHELL_WRITE`.** The refusal names the target and the reason, and gives the fix:
   - Edit for a change
   - Write for a new file
   - `io.edit` (task 24) for a batch, by its callable name
4. **Warn on a script file created inside the worktree (GIT-1),** and suggest the scratchpad.
5. **Port every rule of `shell-write-guard.py`,** each with a test. Then fix SHW-8 with a test that reproduces it.

## Where

`plugins/io-guard/scripts/ioguard/checks/shell_writes.py`, `tests/checks/test_shell_writes.py`.

## Done when

- Replay: someone has looked at every refusal of a command whose recorded result succeeded.
- A random sample of 500 read-only commands gets no refusal.
- The SHW-8 command passes.
- The kit can drop `shell-write-guard.py` (task 30).

## What changed

- **`lib/shell.py`:** `commands` splits a Bash command into `SimpleCommand`s at the operators bash reads
  outside quotes, heredoc bodies and comments. Each carries its unquoted words, its file `Redirect`s and its
  `<` inputs. `2>&1` and `>&2` duplicate a stream and are never a `Redirect` (SHW-8).
- **`lib/pwsh.py`, new:** `commands` does the same for PowerShell, with `''` and backtick escapes,
  here-strings and `<# #>` comments. `file_calls` finds the literal paths of `[IO.File]` write calls.
- **`checks/shell_writes.py`, new, `shell.writes`:** finds each write a command makes: `>` and `>>`, `sed -i`
  and `perl -i`, `tee`, `cp`, `mv`, a heredoc or `python -c` body that opens a file for writing, a body
  `transport.body` moved into a file, and `Set-Content`, `Add-Content`, `Out-File`, `Tee-Object`,
  `Copy-Item`, `Move-Item` and `[IO.File]`. It follows `cd` and `Set-Location` through the chain. It refuses
  with `SHELL_WRITE` only when git tracks the target, naming the target, the route and the Edit or Write tool.
  A target in the scratchpad, on a device, outside any repository, built from a variable, or after a `cd` it
  cannot follow passes. A script created inside a repository gets a `SHELL_WRITE` warning that names the
  scratchpad (GIT-1). Git is asked once per path per session, in `SessionState.tracked`.
- **Order:** `transport.body` runs after `shell.writes`, so a refused command never has a body moved first.
  `CHECKS` is `(SessionProbe, ShellWrites, TransportBody)`, and `SHELL_WRITE` is in `CODES`.
- **Replay:** `SnapshotGit` answers from each repository's `git ls-files`, read once per repository.
- **io-guard is for anyone's projects:** the lead's rule, added to `.claude/rules/this-repo.md`. The corpus label
  `guard-refused` became `hook-refused`, matching any PreToolUse hook's refusal. The command line's example and
  the design's examples name `myproject` and `shared-lib`.
- **Not built:** the fix does not name `io.edit`, which does not exist yet. Task 24 carries it in its notes.
- **Tests, 319 in all, up from 292:** `tests/checks/test_shell_writes.py` (17), `tests/lib/test_pwsh.py` (5),
  and `commands` cases in `tests/lib/test_shell.py`. Each rule of the kit's `shell-write-guard.py` has a test
  that refuses its write to a tracked file, and so does its here-string rule.
- **Docs:** `docs/design/architecture.md` sections 1, 2, 3, 4 and 11, `context.md` (the label rename and the
  rebuilt corpus, and the codes paragraph), `README.md` (the status line, the fixes table, the example's real
  text), `CLAUDE.md` (the layout line and the corpus example), and task 24. The drawing's Checks box already
  covers it. No live check ran, so `compat.md` and `live-checks.md` stay as they are.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- **Replay over 180,478 calls, 82 s:** of 101,623 Bash and PowerShell calls that ran, `shell.writes` refused 259,
  0.25%: `sed -i` 93, a `>` redirect 76, a script body 51, `cp` 29, `Move-Item` 7, `mv` 3. Read by group and by
  target, every one writes a file git tracks today. The 10 renames and some `cat >` creations made a file that
  git tracks only now, so the replay refuses them and a live session would not. None of the 259 is a command
  that writes nothing. 4 failed calls were refused too.
- **GIT-1:** 37 warnings on calls that ran, each a scratch script created inside a repository. Before `cd` was
  followed there were 1,414, nearly all scripts written after a `cd` into the scratchpad.
- **500 read-only commands**, drawn with a fixed seed from 7,637 Bash calls that ran, where every simple command
  is a reader such as `ls`, `grep` or `git status`: 500 OBSERVE, no refusal and no warning.
- **SHW-8:** `git commit -m @'...'@ 2>&1 | Select-Object -Last 6` passes, as a test.
- **GRD-1, twice live:** the kit's guard refused this session's own commands. Once a Python heredoc held
  `cat > notes.md <<'EOF'` as data. Once a read-only grep's pattern held the words, and the guard answered
  "shell-write-guard refused this command: an in-place edit by sed or perl." Both forms pass `shell.writes`,
  as tests.
- `python -m unittest discover -s tests -t .` ran 319 tests, all passing.

Not checked:

- **A live session.** The Done-when needs none. The refusal's route to the model was checked live in task 08
  (`live-answers`).
- **How many `cat >` refusals are creations.** The replay reads today's git, which cannot tell a creation
  from an overwrite.
- **macOS.** CI runs the tests there. Nothing in the check differs by platform except the MSYS drive form
  `/c/`, which only Windows reads.
- **Dropping the kit's guard.** Every rule of it is ported with a test, and task 30 removes it.
