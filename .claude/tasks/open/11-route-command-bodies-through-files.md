---
title: Route command bodies through files, under the user's rewrite mode
stage: B
area: transport
created: 2026-09-27
status: open
depends-on: [03, 08, 09, 10]
findings: [SHW-2, SHW-3, SHW-4, SHW-6]
platforms: [windows, macos]
commit: "feat: move heredoc and inline-script bodies into files before they run"
---

## Why

This is the largest token sink in the baseline. 241 Bash commands failed at the ~7.8 KB cut, carrying 2.0 MB,
about 531k tokens. Between 8 and 16 KB, 160 of 160 failed. The same transport halves every `\\` (SHW-2), which
corrupts written files and empties regex matches without an error (SHW-3). The fix suggested in #92543 is this
task: hand the script to bash through a file. Moving the body also removes the quoting hazards on macOS.

A rewrite is also an approval. A hook `allow` skips the permission prompt and the auto-mode classifier, so a
silent rewrite would run a command nobody judged. The user's rewrite mode decides what happens (D12).

## What to build

A PreToolUse check on Bash, and on PowerShell where the forms exist:

- **Detect a body:**
  - a heredoc: `<<'X'`, `<<X`, `<<-X`
  - an inline script: `python -c "..."`, `node -e`, `pwsh -Command`, `bash -c`
  - `python -` fed by a heredoc
- **Quoted heredoc** (no expansion inside). Write the body's bytes to `<scratchpad>/io-guard/body-<hash>.<ext>`,
  using `scratchpad_dir` from the hook input. Then rewrite the command so the program reads that file:
  - `python - <<'PY' ... PY` becomes `python "<file>"`
  - `cat <<'EOF' | prog` becomes `prog < "<file>"`
  - `cat > out <<'EOF'` is a file write, and task 12 decides it

  Keep the rest of the command exactly as written.
- **Unquoted heredoc** (the shell expands `$x` and backticks inside). Moving it would change its meaning, so leave
  it. The budget and backslash checks still apply.
- **`-c` and `-e` bodies with no shell expansion inside** move the same way: `python -c "<body>"` becomes
  `python "<file>"`.
- **The rewrite mode.** `transport.rewrite_mode[permission_mode]` picks the answer (D12). `refuse` denies the call
  with the rewritten command as the fix, so the model reruns it and the classifier judges it. `ask` answers `ask`
  with `updatedInput`. `allow` answers `allow` with `updatedInput`. The defaults: `refuse` in auto and dontAsk, `ask`
  in default, acceptEdits and plan, `allow` in bypassPermissions. The body file is written in every mode, so the
  fix points at a file that exists.
- **Budget.** After any rewrite, a command still over the budget is refused with `TRANSPORT_BUDGET`. Its fix says
  to Write the script and run the file. The budget is the smallest of three: the key `transport.budget_bytes`,
  6,000 by default, which this task adds, `ctx.probe.transport_budget`, the Bash tool's cut that task 10's probe
  records (7,807 on Windows, None where no cut exists), and `SessionState.budget_override` from task 22. With
  no cut in the probe, the check applies no budget.
- **Backslashes.** On Windows, a `\\` left in a command that was not moved gets `BACKSLASH_TRANSPORT`: refused,
  with the moved-body fix.
- **Report every rewrite**, for example "moved a 9.1 KB heredoc body to <file>, ran python <file>".

## Where

`plugins/io-guard/scripts/ioguard/checks/transport_body.py`, `lib/shell.py`, `tests/checks/test_transport_body.py`.

## Done when

- Live on Windows in the default permission mode: a 9 KB `python - <<'PY'` body is shown for approval with the
  rewritten command, runs, and `len(r"\\n")` inside it prints 3.
- Live on Windows in auto mode: the same call is refused, and the rerun of the fix runs.
- Replay covers both sides:
  - every one of the 203 failing heredoc commands is rewritten, or refused with a fix
  - of the 19,698 heredoc commands that passed, fewer than 0.1% get a rewrite that changes what they do, checked
    by hand on a sample
- The tests pass in CI on both platforms, and short commands run untouched.

## Notes

- The moved bodies stay in the session scratchpad and are never committed.
- `updatedInput` combines with `allow` or with `ask` (`context.md`). Task 03 items 13 and 14 confirm what each
  shows on this harness.
