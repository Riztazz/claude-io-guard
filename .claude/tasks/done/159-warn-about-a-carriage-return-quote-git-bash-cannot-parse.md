---
title: Git Bash fails to parse a carriage return quote in a later $() of one double-quoted string
stage: I
area: checks
created: 2026-10-01
status: done
depends-on: []
findings: []
platforms: [windows]
commit: "feat: shell.lint warns about a CR quote Git Bash cannot parse"
---

## Why

A Bash call in this repository's session failed on 2026-10-01 with only this:

```
/usr/bin/bash: eval: line 9: unexpected EOF while looking for matching `)'
```

The command counted line endings with `$(grep -c $'\r$' "$S/SmartTable.h")` twice in one `echo "..."`. The lead:
"can we fix that with io-guard, what do you think? or its just poor script itself?", then "Let's put a warn on it
then, without the 'cr=$'\r'' fix".

## What was found

Git Bash 5.2.37 fails on its own, with no Claude Code in between: `bash file.sh` and `bash -c` give the same
error. Each shape below ran through Git Bash's `bash.exe -c` on 2026-10-01:

| Shape | Result |
|---|---|
| `"$(echo a) $(echo $'\r')"` | fails |
| `"$(echo $'\r') $(echo $'\r')"` | fails |
| `"$(echo $'\x0d') $(echo $'\x0d')"` | fails |
| `"$(echo $'\r') $(echo a)"`, the CR in the first `$()` | runs |
| `"$(echo $'\t$') $(echo $'\t$')"`, `\n` the same | runs |
| `$(echo $'\r') $(echo $'\r')`, no outer double quotes | runs |
| `"$(echo $'\r')" "$(echo $'\r')"`, a string each | runs |
| `"$(echo $'\r' $'\r')"`, one `$()` | runs |
| `$'\015'`, `$'\cM'`, `$'\u000d'`, `$'\x0da'` in the second `$()` | fail |
| `$'\\r'` and `$'\\x0d'` in the second `$()`, a CR only after a second decode | fail |
| `$'\\\\r'` and `$'\\t'` in the second `$()` | run |
| `'\r'` in single quotes, and a literal CR byte | run |
| the quote nested deeper inside the second `$()`, or in a new string there | fails |
| the quote nested inside the first `$()` | runs |
| `"$(( $(echo 1) + $(printf $'\r') ))"`, with or without the outer quotes | fails |
| `$((1))` or a backtick substitution as the first one | runs |
| `$(echo a)"$(echo $'\r')"`, `"$(echo a)"x"$(echo $'\r')"`, `$(echo a)$(echo $'\r')`: one word, any quotes | fail |
| `echo $(echo "$(echo a) $(echo $'\r')")`: the word sits inside a `$()` | runs |
| a newline on another line, before or after the word | fails, and the word's line never runs |
| a newline inside the word before the quote: between the `$()`, or inside the second before the quote | runs |
| a newline inside the first `$()` | fails, and is not caught |

So the trigger is a `$'...'` that makes a carriage return after one decode or two, anywhere inside the second
or a later `$()` of one shell word, when that word is outside every `$()`. Quotes around the `$()` don't
matter, a `$(( ))` is part of its word, and only `$()` counts toward first. Fable's review of 2026-10-01 found
the word boundary. Whether Linux or macOS bash fails too is not known: WSL here has no distribution with bash,
and the Mac is down (D21). The warning fires on Windows only.

## What changed

- `lib/shell.Scanner` records each such quote in `Scan.carriage_returns`. `normal` starts a new word at each
  separator outside every `$()`. `counted` counts a word's `$()` from `normal`, `double` and `arithmetic`
  alike, and marks everything inside the second and later ones late. `ansi` checks a late quote with
  `ansi_decoded`, a decoder for every `$'...'` escape, unless the word holds a newline before the quote.
- `arithmetic` now scans a `$()` inside `$(( ))` as one. Before, it counted every parenthesis, a quoted one
  too. Over the corpus this changes one command's scan: it read as unterminated, and it now reads as the
  complete command it was, which ran.
- `shell.lint` warns with `CR_QUOTE_UNPARSED` on Windows. The command still runs. The fix it names: "Put that
  $() first in its word, or set a variable to it before this command and use the variable." Both ran in Git
  Bash for a string and for `$(( ))`. The lead asked for no `cr=$'\r'` fix.
- A first version walked the command with a second parser of its own. A review in this session replaced it:
  that parser read a `'` in a `#` comment as a quote, took `\x0da` as one escape, and missed both `$(( ))` and
  the quotes nested deeper. Its second version counted per double-quoted string and skipped every command
  with a newline. Fable's review showed five failing shapes it missed, three running shapes it flagged, and
  multi-line commands that fail.

Evidence:

- `test_the_carriage_return_quotes_git_bash_fails_to_parse_are_found` in `tests/lib/test_shell.py` holds 26
  shapes Git Bash failed and 19 it ran, and `test_it_is_a_warning_on_windows_and_nothing_elsewhere` in
  `tests/checks/test_lint.py` the check on Windows and macOS. Both failed first. A scratch script ran all 45
  through Git Bash and found each list's claim true.
- `python tests/run_all.py`: 1,144 tests, OK, 2 skipped, with task 160's test.
- `python tools/ioguard.py check` on the command that failed gives the warning.
- The corpus's 58,779 Bash calls hold 5 that failed with this EOF message, in CLICKER and OrbitalDrift. The
  scan flags all 5 and no other call.
- HEAD's scanner against this one over every corpus command: only the one command above scans differently.
- Not seen live: the warning in a session. It needs the plugin updated and the app restarted.

Docs: `docs/design/architecture.md` names the code in the package tree and the codes table, and `scan` and
`ansi_decoded` in the `shell` API. The skill's code table is regenerated by `tools/skill.py`.

Checked on Windows 10 on 2026-10-01.
