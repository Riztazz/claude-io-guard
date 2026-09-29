---
title: Hold io.run's wrapped commands and code bodies to the user's permission rules
stage: H
area: checks
created: 2026-09-29
status: done
depends-on: []
findings: [security-review-2026-09-29-2]
platforms: [windows, macos]
commit: "fix: io.run asks before a wrapped command or a code body a rule could meet"
---

## Why

Fable's security review of 2026-09-29, finding 2, high, checked in the code the same day. `run.rules`
(`plugins/io-guard/scripts/ioguard/checks/run_rules.py`) matches the user's Bash and PowerShell deny and ask rules
against `runs.argv_of`, and `lib/rules.py` `unwrapped` strips assignments, `env`, `timeout` and the like, but not
a shell or an interpreter given a string: `bash -c "git push"`, `pwsh -Command ...`, `python -c ...`. A code body
is matched as its interpreter and the body's file path. So a deny rule such as `Bash(git push *)` never meets
`io.run(["bash", "-c", "git push"])` or a body that pushes, and once the user allowed the `io_run` tool, no rule
matching means no prompt. `commit.policy` has the same blind spot for a commit inside a body.

## What to build

- When any deny or ask rule applies to the session, `run.rules` answers ask for every code body and every argv
  whose program is a shell or an interpreter given a command string, naming why.
- Where the wrapped string parses as one command, it is matched as that command too, so a deny rule refuses it.
- `commit.policy` reads a body's lines for a git commit.
- Replay over the corpus before shipping, since this asks more often: the false asks stay under 0.1%.

## Done when

- `io.run(["bash", "-c", "git push"])` is refused under a `Bash(git push *)` deny rule, and a Python body asks
  under any ask rule, live through a probe.

## What changed

- `lib/rules.py`: `wrapped` names the command string a shell or an interpreter in an argv is given: `bash`,
  `sh` and the like with `-c` or a combined flag such as `-lc`, `pwsh` or `powershell` with `-Command`, an
  `-EncodedCommand` decoded from base64 UTF-16LE, Windows PowerShell's bare command, `cmd /c`, and
  `python -c`, `node -e` and the other code flags. `inner` splits a shell string into its simple commands, or
  gives up on a command substitution, a process substitution, `eval`, `source` or a call through a variable.
  `match_command` matches each inner command, NESTED (4) shells deep, deny first, then ask, then "unread".
  `rule_named` finds a deny or ask rule whose program the text names as a whole word.
- `checks/run_rules.py`: `judge` uses `match_command`, and a `code` body is searched with `rule_named`. An
  unread string or a body that names a rule's program asks with `RULE_ASKED`, naming the rule. `said` gives
  the whole reason, so `mcp/tools_run.py` shares it.
- `checks/commit_policy.py`: an `io.run` call's shell string, and a Bash or PowerShell body, are read for
  `git commit` messages like a Bash or PowerShell command. A body in another language is left unread.
- **A change from the task text, D41:** an unread string or a body asks only when it names a rule's
  program, not whenever any rule exists. Over the corpus, 9,825 of 58,779 Bash calls (16.7%) hold a code
  string, so asking on each would prompt on one call in six for a user with any rule. Naming a rule's
  program cut that to 31 (0.053%) under `Bash(git push *)` denied and `Bash(git fetch *)` asked, under the
  0.1% bar. Code can spell a program in parts, and a script an argv runs is read by neither Claude Code nor
  io-guard. The corpus holds no `io.run` call, so the Bash calls stand in for them. The lead's own settings
  hold no Bash or PowerShell deny or ask rule, so none of this asks in the lead's sessions.
- `tests/mcp/test_tools_run.py`: only `TheUsersRulesHold` writes the rules, since a `python -c` naming no
  rule's program never asks.
- `tools/probes/run_probe.py`: `live-run-wrapped`.
- Docs: `docs/design/architecture.md` (the rules API and section 5), `README.md`, `docs/live-checks.md`,
  `docs/compat.md`, and D41 in `context.md`. The drawing states nothing this changed.

Evidence:

- `python tests/run_all.py`: 936 tests, OK, up from 926. New: each shell form's string is read, a script file
  or a program's own flag is not a string, code strings and `cmd /c` are unread, a rule meets a command
  inside a string at any depth (deny, ask, none, unread, a decoded `-EncodedCommand`), nesting past NESTED is
  unread, a program counts only as a whole word, `bash -c "git push"` is denied at the hook, a body or an
  unread string naming git asks and one naming none does not, and `bash -c`, Bash and PowerShell bodies meet
  the commit policy.
- Live, Claude Code 2.1.283 on Windows: `live-run-wrapped` passes (20260929-124128): `bash -c "git push
  origin main"` was refused with `RULE_DENIED`, and the body running `git fetch` reached the permission
  prompt with `RULE_ASKED`. `live-run-denied`, `live-run-asked` and `live-commit-policy` pass again.

Checked on Windows 10 on 2026-09-29. Not checked: macOS live (task 36).
