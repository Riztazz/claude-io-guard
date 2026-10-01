---
title: PowerShell stops and writes io-guard misses, and one it misreads
stage: I
area: lib
created: 2026-10-01
status: done
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

## What changed

- `lib/kills.py`: a `Get-Process` stop now reads across one `Where-Object`, `where` or `?` filter before
  `Stop-Process`, `spps` or `kill`. `pkill -f` is matched case by case, so `pkill -F`, a pidfile stop, is no
  longer read as a match on command lines.
- `lib/pwsh.py` `commands()` drops a leading `&` or `.` when a literal program follows it, so `& "x.exe"`
  names `x`. A call through a `$variable` keeps its operator, which `rules.statement` reads to tell a call from
  an expression. An existing test, on `& $tool push`, caught that case during the change.
- `lib/writes.py` `powershell_writes` reads each `{ }` script block, up to `rules.BLOCKS` deep, and drops exact
  duplicates, since an `[IO.File]` call in a block is found in the whole command too.
- `positional()` takes an option's next word as its value unless the option is a known switch, such as
  `-Force` or `-NoNewline`, or gives its value after a colon. `PS_SWITCHES` lists the switches. So
  `New-Item -ItemType File -Force foo.txt` writes `foo.txt`.

Evidence:

- New cases failed first: 3 stop shapes in `tests/lib/test_kills.py` (2 found, 1 by id left alone) and
  `pkill -F run.pid`, `test_a_call_operator_is_not_the_program` in `tests/lib/test_pwsh.py`, and 8 shapes in
  `test_writes_inside_script_blocks_and_after_value_options_are_found` in `tests/lib/test_writes.py`.
- Replay over the corpus, HEAD against this change: one difference. `shell.writes` refuses one more call that
  ran, 212 against 211. It is a PowerShell `if (...) { ... Set-Content }` that rewrote a tracked `.cpp` file in
  OrbitalDrift. The same write outside a block was refused already, so this is the policy reaching a write it
  could not see, not a false refusal.
- Over the corpus's 3,321 PowerShell calls, 49 have different write targets. Most read `-ItemType Directory`'s
  `Directory` as the path before and now read the real target, often a `$variable`, which resolves to no
  tracked file.
- `python tests/run_all.py`: 1,152 tests, OK, 2 skipped, against 1,150.

Docs: `docs/design/architecture.md` says `pwsh.commands` drops a literal call's operator and
`powershell_writes` reads script blocks.

Checked on Windows 10 on 2026-10-01.
