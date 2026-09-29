---
title: Read a wrapped shell's command the way bash and PowerShell do, so a deny rule holds
stage: I
area: lib
created: 2026-09-29
status: claimed
claimed-by: Pala Elektroniczna, the claude_io_guard session of 2026-09-29
depends-on: []
findings: []
platforms: [windows, macos]
commit: "fix: io.run meets a deny rule however the wrapped command is spelled"
---

## Why

The code review of 2026-09-29, slice B, item 1, rated high. `rules.match_command` reads the command inside
`bash -c` and `pwsh -Command` (D41), but `lib/shell.py`'s scanner and `lib/pwsh.py` read some forms another way
than the shell does. The string then counts as read, holds no `git push`, and D41's ask for an unread string
never fires. Checked on Windows on 2026-09-29, with `Bash(git push *)` and `PowerShell(git push *)` denied:

| The wrapped string | match_command |
|---|---|
| `git push origin` | deny |
| `git \` then a newline, then `push origin` | none: `unquote` keeps the newline, so the words are `git` and `\npush` |
| `(( 1 << 2 ))`, a newline, `git push origin` | none: `<<` inside `(( ))` is read as a heredoc with the delimiter `2` |
| `cat <<$'EOF'`, `x`, `EOF`, `git push origin` | none: the delimiter is read as `$EOF`, which never ends. bash runs the last line |
| `& { git push }` for pwsh | none: the script block is one word |
| `if ($true) { git push }` for pwsh | none |

`io.run`'s own `checked()` calls the same `judge`, so the tool does not catch it either.

## What to build

- `lib/shell.py`: a backslash before a newline outside single quotes is a line continuation and both go. `<<`
  inside `(( ))` and `$(( ))` is a shift. A heredoc delimiter is unquoted the way bash does, `$'EOF'` and
  `"EOF"` included.
- `lib/pwsh.py`: the commands inside a script block, `& { }`, `. { }`, an `if`, `foreach`, `while` or `switch`
  body, and a `ForEach-Object` or `Where-Object` block, are read as commands.
- The rule under all of it: a form the scanner does not model makes the string unread, never read wrongly. An
  unread string that names a rule's program asks, as D41 says.
- A test per row above, in `tests/lib/test_rules.py`, each giving deny.

## Where

`lib/shell.py` (`Scanner`, `unquote`, the heredoc reader), `lib/pwsh.py`, `lib/rules.py` (`inner`,
`match_command`).

## Done when

- Every row above gives deny, and the plain forms still match as before.
- A replay over the corpus keeps D41's asks at or under 0.1% of `io.run`-shaped calls.
