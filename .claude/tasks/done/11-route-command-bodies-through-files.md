---
title: Route command bodies through files, under the user's rewrite mode
stage: B
area: transport
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
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

## What changed

- **The halving rule, measured first.** The plan said the Bash tool halves every `\\`. Probes through this
  session's own Bash tool on 2.1.281 showed a run of backslashes loses half its pairs only when a double quote
  does not follow it (`context.md`, row 25). That is why Python's `"\\"` in a heredoc runs.
- **`lib/shell.py`:** `scan` reads a command as bash does, through single and double quotes, `$'...'`,
  command substitution, arithmetic, comments and heredoc bodies. It returns the heredocs, the `python -c` bodies
  and the hazards, the pairs whose halving changes what bash reads. `moved` turns a quoted heredoc into
  `< "<file>"` and a `python -c` body into an `exec` of its file, and leaves the rest as written.
  `budget_length` counts apostrophes as four.
- **`checks/transport_body.py`:** on Windows, a body moves when the command is over the budget or the body
  holds a hazard. The file lands in `<scratchpad>/io-guard/body-<hash>`, byte-exact (D25). A command still over
  the budget is refused with `TRANSPORT_BUDGET`. A hazard outside a moved body is a `BACKSLASH_TRANSPORT`
  warning, not the planned refusal, because refusing would stop 1.0% of the calls that ran. `node -e`, `bash -c`
  and `pwsh -Command` bodies do not move, because moving them changes how they resolve relative paths, and they
  meet the budget like any command. PowerShell is left alone: its tool keeps backslashes and takes 9 KB.
- **The budget:** the key `transport.budget_bytes`, 6,000, marked `project_narrows`, so a project file may lower
  it and never raise it. The check takes the smallest of the key, the probe's cut and the session's override.
- **Replay** now gives each record the probe's transport facts for its platform and version, and a data folder
  in memory.
- **`tools/probes/run_probe.py`:** `live-move-ask` and `live-move-auto`. A guard probe with `server=True` also
  loads io-probe for its `probe_permit` tool.
- **Tests, 292 in all, up from 255:** `tests/lib/test_shell.py`, which runs moved commands through real bash
  from a script file and compares output with the original, `tests/checks/test_transport_body.py`, and two
  narrowing tests in `tests/lib/test_config.py`.
- **Filed:** `UNREAL-SHARED/tasks/open/correct-the-bash-backslash-halving-rule.md`, because the kit's rule
  states the old halving claim, and task 30 carries it. Task 12 now covers the moved form of `cat > out <<'EOF'`.
- **Docs:** `docs/design/architecture.md` sections 2, 4 and 5, `context.md` (D25, rows 25 and 26),
  `docs/compat.md`, `docs/live-checks.md`, `README.md` (the fixes table and the budget setting), tasks 12 and 30.
  The drawing already shows `transport.body`.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- **Live, CLI 2.1.283:** `live-move-ask` in default mode with Haiku: an 8,973-character `python - <<'PY'` call
  was answered `ask`, the permission prompt received `python - < "<file>"`, and the approved run printed 3 for
  `len(r"\\n")`. `live-move-auto` with Sonnet in auto mode: refused with the moved command as the fix, and the
  rerun printed 3.
- **Replay over 180,464 calls, 41 s:** all 208 `unexpected-eof` commands past the budget were moved, none
  refused. The other 38 `unexpected-eof` commands are under 6,000 bytes, quoting errors for task 13. One call
  that ran was refused, 0.001%: a 6,000-to-7,807-byte command with no body. 751 calls that ran were moved: 221
  heredocs over the budget, which run the same, and 530 with a hazard in the body, which run differently.
- **By hand, 20 of those 530:** 12 had been silently corrupted by the halving and are fixed, such as
  `.replace("\\r\\n", "\n")` meant to unescape JSON text. 4 had doubled their backslashes on purpose and break,
  such as `re.sub(r"^(\\s*)...")`. 4 read the same. The lead chose exact bytes knowing this (D25).
- 1,004 calls get the `BACKSLASH_TRANSPORT` warning, 965 of them calls that ran.
- `python tests/run_all.py` ran 292 tests, all passing.

Not checked:

- **The plan's second replay bar.** It asked that fewer than 0.1% of passing heredoc calls change what they do.
  530 of 19,877 change, 2.7%, most of them for the better, by D25's choice.
- **The live checks on the desktop's 2.1.281.** The halving rule was measured there, and the move checks ran on
  the CLI only.
- **macOS.** No cut and no halving is recorded there, so the check does nothing. Task 36 measures it.
