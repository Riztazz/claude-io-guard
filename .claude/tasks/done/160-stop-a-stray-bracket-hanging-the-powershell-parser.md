---
title: A PowerShell command with a stray closing bracket hangs the io server's worker
stage: I
area: lib
created: 2026-10-01
status: done
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: a stray closing bracket no longer hangs the PowerShell parser"
---

## Why

Fable's review of 2026-10-01, item 1, re-run by this session the same day: `pwsh.commands("Write-Host 'x' }")`
and `pwsh.commands("echo a)")` were still running after 5 s, and `pwsh.commands("Write-Host 'x'")` returned.

In `lib/pwsh.py`, `commands()` hands an unmatched `)`, `]` or `}` to `word_at()`, which returns the offset it
was given, so the loop never moves. The redirect branch does the same on `echo a > )`. Every PowerShell call
reaches it, through `shell.lint`, `shell.writes`, `commit.policy` and `shell.touched`, and so does a Bash
`pwsh -Command "..."` through `lib/writes.py`, and `io.run` with a pwsh argv through `lib/rules.py`. Each such
call holds one of the io server's four workers for the rest of the session, and the hook waits out Claude
Code's timeout. None of the corpus's 3,321 PowerShell calls has the shape yet.

## What to build

- `pwsh.commands()` always moves forward: a character no branch reads is its own word, or is skipped.
- A test with each shape Fable found, run with a time limit, so a hang fails the test instead of the suite.

## Where

`plugins/io-guard/scripts/ioguard/lib/pwsh.py`, `commands()` and `word_at()`, and `tests/lib/test_pwsh.py`.

## Done when

- `Write-Host 'x' }`, `echo a)`, `echo a ]`, `(echo a) )`, `Get-ChildItem | % { $_.Name } }` and `echo a > )`
  each return from `pwsh.commands()` at once.

## What changed

`pwsh.commands()` steps past a `)`, `]` or `}` that `word_at()` reads as a word of no length, and a redirect
whose target is such a word records no redirect. The stray closer names no word, since PowerShell refuses the
command anyway.

Evidence:

- `test_a_stray_closing_bracket_is_passed_over_and_never_stops_the_parse` in `tests/lib/test_pwsh.py` runs
  all six shapes in a thread with a 5 s limit. It failed first with the thread still alive and nothing
  parsed, and now passes in under a millisecond.
- `python tools/ioguard.py check --tool PowerShell "Write-Host 'x' }"` and
  `python tools/ioguard.py check 'pwsh -Command "Write-Host x }"'`, which hung past 15 s in Fable's run, both
  answered in 0.7 s together.
- `python tests/run_all.py`: 1,144 tests, OK, 2 skipped, against 1,143.
- Not seen live: the fix in a session. It needs the plugin updated and the app restarted.

Docs: none. No signature, code, setting or tool changed.

Checked on Windows 10 on 2026-10-01.
