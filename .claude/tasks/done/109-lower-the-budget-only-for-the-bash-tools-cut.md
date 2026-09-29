---
title: Lower the Bash budget only for the Bash tool's own cut
stage: I
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: [SHW-4]
platforms: [windows, macos]
commit: "fix: only the Bash tool's own cut lowers the command budget"
---

## Why

The code review of 2026-09-29, slice A item 6. `checks/command_results.py` `budget()` lowers the session's
budget for any failed, well-formed Bash command over 5,000 bytes whose output holds "unexpected EOF while
looking for matching". That line also comes from a script the command ran: `cat > f <<'EOF' ... EOF; bash f`,
5,061 bytes, where `f` has an unclosed quote, set `budget_override` to 5,069 on darwin. Every later command
over that length was then refused with `TRANSPORT_BUDGET` for the rest of the session, though macOS has no cut.

## What to build

- The budget drops only when the error is the Bash tool's own: bash's `-c: line N:` form, which the
  transport cut gives (context.md, the verified live table), and not a `<file>: line N:` from a script.
- On macOS the budget drops only after two such failures, since no cut is known there, and the message says so.
- A test for the script case on each platform.

## Where

`checks/command_results.py` (`budget`), `lib/output.py` if the error pattern lives there.

## Done when

- The script case leaves the budget alone, and task 22's EOF cases still lower it.

## What changed

- `checks/command_results.py`: `budget` reads `CUT`, a line that starts `bash: -c: line N: unexpected EOF`,
  with any folder before `bash`, the form the Bash tool's own bash gives. A script's `f: line 3:`, an `eval:`
  line and a bare `bash: line 1:` lower nothing. On macOS the first cut only warns, with
  `TRANSPORT_BUDGET` saying a second one lowers the budget, and `SessionState.first_cut` holds its length,
  so the second sets the budget below the shorter of the two.
- Tests, each failing first (7 failures): the three other error forms on Windows and macOS leave the budget
  alone, and macOS lowers it at the second cut (`tests/checks/test_command_results.py`). The fixture's EOF
  line is now the measured `-c:` form. The suite of 1,010 passes on Windows, 2 skipped.
- Corpus: of 121 recorded failed Bash calls with an unexpected EOF, 98 read `/usr/bin/bash: -c: line N:`, all
  over 5,000 bytes, and 23 read `/usr/bin/bash: eval: line N:`, all under. Replayed one call per fresh
  session, 98 lowered the budget on HEAD and on the change alike, so no recorded cut is lost. The corpus
  holds no script case.
- `live-results` passed on the CLI 2.1.283 with the change loaded.
- Docs: `docs/design/architecture.md` (`SessionState`, the transport budget paragraph).
- Checked on Windows on 2026-09-29. The macOS path runs only in the unit tests until the Mac is back
  (task 36), and no live macOS cut has been seen.
