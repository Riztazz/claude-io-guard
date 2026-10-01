---
title: PowerShell stops and writes io-guard misses, and one it misreads
stage: I
area: lib
created: 2026-10-01
status: open
depends-on: [160]
findings: []
platforms: [windows, macos]
commit: "fix: io-guard reads PowerShell stops, blocks and New-Item paths"
---

## Why

Fable's review of 2026-10-01, items 6, 7 and 8, each run by Fable.

- `lib/kills.py` misses the common stop idiom: `Get-Process | Where-Object {$_.ProcessName -eq 'python'} |
  Stop-Process -Force` and `Get-Process | ? { $_.Path -like '*node*' } | kill` give no STOPS_BY_MATCH. The
  pattern from get-process to stop-process cannot cross the filter's `|`.
- `pkill -F run.pid` reads as `pkill -f`, since the pattern runs case-blind, and gets a warning for a pidfile
  stop.
- A call operator is read as the program: `& "C:\tools\x.exe" -a > out.txt` names `&`, so lint's rules and
  the write finder's list never match a `& ...` call.
- Writes inside a script block are not seen: `if (Test-Path x) { Set-Content -Path a.txt -Value 1 }` and
  `ForEach-Object { Out-File b.txt }` give no write, so a tracked-file write inside `if`, `& {}` or `foreach`
  passes `shell.writes`. `lib/rules.py` already walks blocks with `powershell_parts`.
- `New-Item -ItemType File -Force foo.txt` reads its target as `File`, since `positional()` skips the value
  only after a few options.

## What to build

- The stop pattern crosses a `Where-Object` or `?` filter, and `-F` stays a pidfile.
- `pwsh.commands()` strips `&` and `.` the way `statement()` does now.
- `powershell_writes` walks `pwsh.script_blocks` as `powershell_parts` does.
- `positional()` skips the value of every option that takes one, `-ItemType` included.

## Where

`lib/kills.py`, `lib/pwsh.py`, `lib/writes.py`, and their tests.

## Done when

- Each shape above gives the result PowerShell would, in a test, and the replay shows no new refusal of a call
  that ran.
