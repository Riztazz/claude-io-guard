---
title: Lower the Bash budget only for the Bash tool's own cut
stage: I
area: checks
created: 2026-09-29
status: open
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
