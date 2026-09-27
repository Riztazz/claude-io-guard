---
title: Refuse shell writes to tracked files, and port the kit's current guard
stage: B
area: transport
created: 2026-09-27
status: open
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
