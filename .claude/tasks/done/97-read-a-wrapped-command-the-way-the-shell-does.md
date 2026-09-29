---
title: Read a wrapped shell's command the way bash and PowerShell do, so a deny rule holds
stage: I
area: lib
created: 2026-09-29
status: done
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

## What changed

- `lib/shell.py`: `unquote` drops a backslash and the newline after it, outside single quotes, and
  `commands` skips one between words, so `git \` then a newline then `push` is `git push`. `Scanner` reads
  `((` at a command's start, or after `for`, as arithmetic through `command_position`, so `<<` inside it is
  no heredoc. `arithmetic` takes the offset of its first parenthesis, for `$((` and `((` alike. A heredoc
  delimiter written `$'EOF'` or `$"EOF"` is `EOF`.
- `lib/pwsh.py`: `script_blocks` gives the text of each outermost `{ }` outside strings and comments.
- `lib/rules.py`: `inner` drops a bash `(( ))` command, and treats a heredoc with no end as unread.
  `powershell_parts` reads each script block's commands, up to `BLOCKS` (16) deep. `statement` gives the
  command a PowerShell statement runs: the right side of an assignment, a call through `&` or `.`, and
  nothing for an expression such as `$_.Line`, which the old code read as a call through a variable.
- Tests: `tests/lib/test_rules.py` has the eight rows of `## Why` and a `for (( ))` row, each giving deny, a
  heredoc with no end giving unread, and six PowerShell statements. `tests/lib/test_shell.py` has the
  arithmetic, `$'EOF'` and line-join cases. `tests/lib/test_pwsh.py` has `script_blocks` with braces in a
  string and a comment. Each new test failed first: 8 in `test_rules`, 6 in `test_shell` against the old
  `lib/shell.py`, 4 PowerShell statements, and the block test with the blanking taken out. The suite went
  from 965 to 972, all passing, on Windows.
- A replay of every recorded command, wrapped as `io.run` would get it (`bash -c` for 58,779 Bash calls,
  `pwsh -Command` for 3,321 PowerShell calls), under `git push` denied and `git fetch` asked:

  | | Before | After |
  |---|---|---|
  | Bash unread | 669 (1.138%) | 672 (1.143%) |
  | PowerShell unread | 106 (3.192%) | 55 (1.656%) |
  | Bash deny and ask | 8 and 5 | 8 and 5 |

  The 3 new Bash cases each run `$M call ...` after a backslash and a newline, a call through a variable
  that the old reading hid. The PowerShell drop is `ForEach-Object { $_.Line }` and the like, no longer read
  as a call. This replay wraps whole recorded commands, not D41's code strings, so its level was above 0.1%
  before the change too. The corpus holds no real `io.run` call.
- `tools/probes/run_probe.py`: `RUN_WRAPPED` grants the push in its throwaway folder, since a probe session
  reads the lead's own CLAUDE.md, and this day's first run ended with the model refusing to push.
  `live-run-wrapped` then passed on the CLI 2.1.283.
- Docs: `docs/design/architecture.md` (the pwsh and rules signatures, and section 5's shell string), the
  `lib/rules.py` docstring. `docs/live-checks.md` already dates the probe 2026-09-29.
- Checked on Windows on 2026-09-29. Not checked: the desktop's 2.1.281, and macOS, which waits in task 36.
