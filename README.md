# io-guard

**Your AI agent sends a bad command. io-guard fixes it before it runs, and the agent gets the result it
wanted.**

The agent keeps working on your code. It doesn't lose time, and it doesn't spend tokens trying again and again
to fix errors that come from the shell, not from your code.

io-guard is a plugin for Claude Code. It works on Windows and macOS. It looks at every command and every file
change the agent makes:

- **Before it runs:** when io-guard can fix it, it fixes it, and tells the agent what it changed.
- **When it can't be fixed:** io-guard stops it, and tells the agent what to send instead.
- **After it runs:** io-guard tells the agent what really happened, in clear words, not just "exit code 1".

You can change every rule and every limit, for all your projects or for one.

## It fixes the command before it runs

Agents make the same shell and file mistakes every developer knows. io-guard fixes them before they run:

| The agent sends | Without io-guard | What runs instead |
|---|---|---|
| A long Python script in a heredoc, on Windows | `unexpected EOF while looking for matching ''`. The Bash tool cuts any command near 7.8 KB | The script, read from a file, exactly as written |
| `print("C:\\work\\app")` in a heredoc, on Windows | The Bash tool halves the backslashes. Python reads `\a` as a bell character and prints `C:\work` and junk | The script, read from a file, every backslash kept |
| `cd "C:\work\app\"` | `unexpected EOF`. In bash, `\"` is a quote inside the string, not its end | `cd "C:/work/app/"` |
| `taskkill /F /IM app.exe` in Git Bash | Git Bash turns `/F` into the path `F:/`, and taskkill fails | The same command, with `/F` and `/IM` left alone |
| `dir 2>nul` in Git Bash | A real file named `nul`, which Windows tools can't delete | `dir 2>/dev/null` |
| `python -c "print('\u2192')"` on Windows | `UnicodeEncodeError: 'charmap' codec can't encode character` | The same command, with Python set to UTF-8 |
| A Write over a file with CRLF line endings and a BOM | The file comes back LF with no BOM, and git diff marks every line changed | Your text in CRLF with the BOM. git diff shows only your change |
| An Edit indented with spaces, in a file indented with tabs | Mixed tabs and spaces | Your new lines, indented with tabs |

The agent sees each fix. For the long script:

```
The agent sends   Bash: python - <<'EOF'  ...10 KB of Python...  EOF
What runs         python - < "~/.claude/io-guard/bodies/body-7316d4896518f5c9.txt"
The agent reads   BODY_MOVED_TO_FILE: io-guard moved a 10.0 KB heredoc body to
                  ~/.claude/io-guard/bodies/body-7316d4896518f5c9.txt, and the command reads it from there.
                  The body arrives exactly as written, with no backslash halved.
```

In auto mode, io-guard gives the fixed command to the agent, and the agent sends it again. In the other modes,
you approve it, or it runs at once. You choose this for each mode, in [the settings](docs/settings.md).

## It stops what it can't fix

| The agent sends | io-guard answers |
|---|---|
| `sed -i 's/30/60/' client.py` | Stops it. A shell edit skips io-guard's checks and Claude Code's undo. Use the Edit tool |
| ``git commit -m "fix the `retries` default"`` | Stops it. Bash would run `retries` as a command. Use single quotes |
| A commit with a `Co-Authored-By` line, when you've banned it | Stops it, and the agent commits again without the line |

## It keeps your files clean

- **ASCII where you want it.** When the agent adds a smart quote, an em dash or any other non-ASCII character to
  a file you listed, io-guard reports it with the line number. The pre-commit hook keeps it out of your
  commits, and the commit policy keeps it out of commit messages.
- **No invisible characters.** A zero-width space, a stray BOM or a no-break space is reported with its line
  number, in every file.
- **Line endings put back.** When a write loses a file's line endings or BOM, io-guard puts them back and tells
  the agent.
- **Files changed by other commands.** After a formatter or a script runs, the agent learns which files it read
  have changed, so it reads them again before its next edit.

## It gives clear errors, not just exit codes

A failed command often says only `Exit code 1`. The agent has to guess what went wrong, and it often guesses
wrong. io-guard gives every problem a name, says what happened, and says what to do next:

```
Without io-guard   Exit code 1
With io-guard      EXIT_BENIGN: Exit code 1 is the answer grep gives when no line matches, not a failure.
                   The commands after it in the && chain did not run. Join them with ; instead of &&, or
                   put || true after grep, when that answer is expected.
```

| The agent sees | io-guard adds |
|---|---|
| `pytest \| tail -5` exits 0 while tests fail | The exit code is from tail, so read the output |
| `grep -q todo app.py && ...` exits 1 | 1 means no match, not an error |
| An Edit fails with "String to replace not found" | The closest match, its line, and the exact text to send |
| A long output saved to a file | Its first and last 20 lines and every error line, in the answer |
| `Get-Process python \| Stop-Process` | A warning first: it can stop other sessions' servers too |

io-guard's own tools answer the same way, as JSON: the name, the message, the file and the fix, each in its own
field.

## How it works

1. **Claude Code calls io-guard** before and after each Bash, PowerShell, Read, Edit and Write call.
2. **io-guard's server runs 22 checks**, one for each kind of problem. It's one process per session, so no
   Python starts per call.
3. **The answer goes back:** run it as it is, run a fixed version, or stop it with the fix.
4. **If io-guard itself fails, your call runs anyway.** A broken check is skipped and logged, and you get one
   warning.

<a href="https://riztazz.github.io/claude-io-guard/architecture.svg"><img src="docs/architecture.svg" alt="io-guard's architecture: Claude Code's tools on top, the plugin's io server, checks and lib in the middle, and the files on disk at the bottom, with four numbered flows" width="100%"></a>

**[Open the interactive drawing](https://riztazz.github.io/claude-io-guard/architecture.svg)** to follow each
step. The full design is [`docs/design/architecture.md`](docs/design/architecture.md).

## Install it

1. In claude.ai, open Customize > Plugins and add `Riztazz/claude-io-guard`. Or, in Claude Code, run
   `/plugin marketplace add Riztazz/claude-io-guard`, then `/plugin install io-guard@claude-io-guard`.
2. You need Claude Code 2.1.281 or later, Python 3.14 or later, and on Windows, Git for Windows.
   [`docs/compat.md`](docs/compat.md) says why.
3. There's nothing to set. io-guard finds Python itself. When yours is somewhere unusual, set `IOGUARD_PYTHON`
   to its full path in the `env` block of `~/.claude/settings.json`. [`docs/launcher.md`](docs/launcher.md) has
   the details.

## Change a setting

Your settings live in `~/.claude/io-guard/config.json`, and a project's `.claude/io-guard.json` overrides them
for that project. To change one, ask Claude, such as "turn off shell.lint for this project", or type
`/io-guard:settings` to open the settings page, which also shows what io-guard fixed this week. A project's own
commands never run until you say yes. [`docs/settings.md`](docs/settings.md) lists every setting.

## Its own tools

io-guard also adds 15 tools the agent can call, for jobs the built-in tools can't do safely: `io.edit` for
several edits in one go, `io.run` to run a program with no shell in between, `io.snapshot` and `io.restore` to
undo one task, `io.format` to format only the lines that changed, and more. [`docs/tools.md`](docs/tools.md)
lists them.

## What it never does

- **It never turns off a built-in tool.** The agent keeps Bash, PowerShell, Edit, Write and Read.
- **It never fixes in silence.** Every fix is shown to the agent.
- **It never sends anything anywhere.** Its stats and logs stay in io-guard's folder on your machine.

## What it fixes, by the numbers

From 110,379 file and shell calls in 738 real agent sessions, 2026-06-20 to 2026-09-27:

| What goes wrong | How often | What io-guard does |
|---|---|---|
| A long Bash command fails on Windows, or loses backslashes | 122 failed commands, about 262k tokens | Moves the script into a file and runs it from there |
| Write turns CRLF into LF and drops the BOM | 328 "LF will be replaced by CRLF" warnings | Writes in the file's own line endings and BOM |
| A shell command writes files the edit tools never see | 2,876 shell writes | Stops it and names the right tool |
| Bash reads a command another way than meant | 29 failed commands, 11 more that did the wrong thing | Fixes the path, or stops it with the fix |
| Git Bash turns `/F` into a path, and `2>nul` makes a file | 163 commands, 17 converted paths, 3 redirects to `nul` | Leaves the switch alone, and writes `/dev/null` |
| An Edit misses, or a Read, Grep or Glob path is wrong | 67 misses, 112 stale reads, 175 missing paths | Gives the closest match and the call to make |
| A script changes a file the agent read, and nothing says so | 30 "modified since read" failures | Names each file a command changed |
| An exit code or a pipe hides what happened | 870 exit code 1 failures, 562 errors behind exit code 0 | Says what the exit code means, and names the hidden errors |
| A commit message holds a line you never want | 74 of 339 commits, under one user's rules | Stops the commit |
| A stop by name kills other sessions' servers | 4 commands, one of which killed io-guard in every session 4 times in 8 minutes | Warns, and names the process id to use |

## Work on it

This repository is also the plugin's marketplace. Only `plugins/io-guard/` ships.

- Start with [`.claude/tasks/README.md`](.claude/tasks/README.md), then `context.md` beside it, then the design.
- Run the tests with `python -m unittest discover -s tests -t .`.
- Check one command offline with `python tools/ioguard.py check "<command>"`. It runs nothing.
- After adding a code or a tool, run `python tools/skill.py`. A test fails until you do.
- See what io-guard did this week with `python tools/report.py`.
- After a Claude Code update, run `python tools/probes/run_probe.py run all`, then `verdicts`.
  [`docs/live-checks.md`](docs/live-checks.md) says when each fact was last confirmed.

## License

MIT. See [LICENSE](LICENSE).
