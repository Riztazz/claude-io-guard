# io-guard

A Claude Code plugin that checks what an agent sends to the file and shell tools, fixes what it safely can, and
returns a structured error for the rest. One codebase runs on Windows and macOS.

**Status: in build.** The plugin installs, and its hooks answer every file and shell call. Four checks run so
far: the session probe, the Bash body move, the shell-write refusal and the quoting and dialect lint. The build
plan is in `.claude/tasks/`, and this page describes the plugin the plan builds.

## Five fixes, by example

**A long script on Windows.** The Bash tool cuts a command near 7.8 KB.

```
The call   Bash: python - <<'EOF'  ...9 KB of Python...  EOF
Without    /usr/bin/bash: -c: line 1: unexpected EOF while looking for matching `''
With       io-guard moved a 9.0 KB heredoc body to <scratchpad>/io-guard/body-3f9c2a7b1d4e8f60.py, and the
           command reads it from there. The body arrives exactly as written, with no backslash halved.
```

**A Write over a Windows file.** The Write tool writes LF and drops a BOM.

```
The call   Write: settings.ini, a file with CRLF endings and a BOM
Without    The file comes back LF with no BOM. git diff marks every line changed, and git warns
           "LF will be replaced by CRLF".
With       The content is rewritten to CRLF with the BOM before Write runs. git diff shows only the lines that
           changed, and the model reads EOL_CONVERTED and BOM_RESTORED.
```

**An Edit that misses.** The text the model sends is not quite the text in the file.

```
The call   Edit: client.py, old_string "    retries = 3"
Without    String to replace not found in file.
With       ANCHOR_NOT_FOUND, with the closest match: line 48 holds "\tretries = 3", a tab where the call has
           four spaces. The corrected Edit call comes with it.
```

**A write through the shell.** No check sees it, and rewind can't undo it.

```
The call   Bash: sed -i 's/timeout=30/timeout=60/' src/client.py
Without    The file changes, and nothing records how.
With       Refused. SHELL_WRITE: This command writes C:/work/app/src/client.py, which git tracks, through
           sed -i, so the write skips io-guard's byte checks and Claude Code's checkpoints. Use the Edit tool
           to change it, or the Write tool to replace it whole.
```

**A search that finds nothing.** grep exits with 1 when no line matches.

```
The call   Bash: grep -rn "legacy_api" src/
Without    Exit code 1, and the model reports that the search failed.
With       EXIT_BENIGN: exit code 1 from grep means no line matched. The search worked and found nothing.
```

<a href="https://riztazz.github.io/claude-io-guard/architecture.svg"><img src="docs/architecture.svg" alt="io-guard's architecture: Claude Code's tools on top, the plugin's io server, checks and lib in the middle, and the files on disk at the bottom, with four numbered flows" width="100%"></a>

GitHub shows the drawing as a still image. **[Open the interactive drawing](https://riztazz.github.io/claude-io-guard/architecture.svg)**
to follow each flow step by step, and hover a box to see what it does. The full design is
[`docs/design/architecture.md`](docs/design/architecture.md).

## What it fixes

The numbers come from 110,379 file and shell tool calls in 738 transcripts of real agent sessions, 2026-06-20 to
2026-09-27. Each call counts once.

| What goes wrong | How often | What io-guard does |
|---|---|---|
| On Windows, a Bash command longer than about 7.8 KB fails with "unexpected EOF", and a `\\` that no double quote follows loses a backslash | 122 failed commands, about 262k tokens | Moves a heredoc or `python -c` body into a file, byte-exact, and runs the file. Warns about a halved `\\` it cannot move |
| Write turns a CRLF file into LF and drops its BOM, and Edit trims trailing spaces from the new text | 328 "LF will be replaced by CRLF" warnings | Rewrites the input in the file's own endings, BOM and indent before it runs |
| A failed Edit says "not found" and nothing else | 67 anchor misses, 112 stale reads | Returns the closest match, the file's endings and a corrected call |
| `sed -i`, redirects and scripts write files around the edit tools, so no check and no rewind sees them | 2,876 shell writes | Refuses a write to a file git tracks, names the tool that does it safely, and warns about a script created inside the repository |
| Bash reads a command differently from what was meant: a Windows path's last backslash escapes its quote, a backtick inside double quotes runs as a command, PowerShell syntax goes to the Bash tool, a Python body doesn't compile | 29 failed commands, and 11 more that ran and did the wrong thing | Rewrites the path with forward slashes, and refuses the rest with the fix |
| Long output is cut, and exit code 1 from grep stops a chain | 148 cut results | Labels the exit code and summarises the errors |

## How it works

io-guard hooks around Claude Code's own tools, so Bash, PowerShell, Edit, Write and Read stay exactly where the
model expects them. Before each call it checks the input, and after each call it checks the result.

1. **Claude Code fires a hook** before the tool runs.
2. **The hook calls io-guard's io server**, one long-running process per session that the session's subagents
   share. No Python starts per call.
3. **A pipeline of checks decides.** Each check handles one concern: where a write lands, how a command travels to
   the shell, a file's bytes, a stale view, what a read shows, what a command's output means. The pipeline orders
   them, chains their fixes and stops at the first refusal.
4. **The answer goes back to Claude Code:** let it run with a note, run a fixed version, or refuse with a code and
   the corrected call.
5. **After the call, the result is checked too:** the bytes on disk against the file's profile, the files a shell
   command touched, and the errors in the output.

Every disk read and write goes through one library, `lib`, so the same code protects the hooks, the io tools and the
tests.

### The io tools

A few jobs have no safe built-in tool, so the io server adds them:

| Tool | Job |
|---|---|
| `io.edit` | Several edits in one file, all or nothing, in the file's own endings |
| `io.splice` | Replace the text between two unique markers |
| `io.append` | Add to the end of a file, wrapped and dated |
| `io.run` | Run a program from an argument list with no shell in between, under your Bash and PowerShell rules |
| `io.read_log` | The lines a log gained since the last read |
| `io.format` | Run the formatter over changed lines only |

## What it never does

- **It never disables a built-in tool.** A tool Claude Code can't see is a tool the model routes around.
- **It adds no escaping layer.** Content travels as a tool argument or in a file, never inside a shell string io-guard
  builds.
- **It never fixes silently.** Every fix is reported to the model, and a fix that could change meaning is a refusal
  with the corrected call instead.
- **It never blocks your work because of its own bug.** A check that crashes is skipped and logged, and you get one
  warning per session.
- **Nothing leaves your machine.** Its telemetry holds codes and timings, never file content, and it stays in the
  plugin's data folder.

## Install it

Once the first release is out:

1. In claude.ai, open Customize > Plugins and add `Riztazz/claude-io-guard`. Or, in Claude Code, run
   `/plugin marketplace add Riztazz/claude-io-guard`, then `/plugin install io-guard@claude-io-guard`.
2. You need Claude Code 2.1.281 or later and Python 3.14 or later. [`docs/compat.md`](docs/compat.md) says why
   2.1.281, and what io-guard does when a Claude Code feature it uses is missing.
3. On Windows with Python from python.org, run `/plugin configure io-guard` and set the Python interpreter to
   `python`. The default is `python3`, which on Windows is often the Microsoft Store stub. When the setting
   doesn't start Python 3.14 or later, io-guard says so once at the start of each session, and checks nothing
   until it's fixed.

Until 1.0, installs follow the latest commit. From 1.0 on, releases are tagged.

## Configure it

Every setting has a default, and every default is a setting. Your settings live in `config.json` in the plugin's data
folder, and a project can add `.claude/io-guard.json`. A project file can only make io-guard stricter: it can't add
places to write to or approve commands.

**What happens to a rewritten command** is yours to choose, per permission mode:

| Mode | Default | What you see |
|---|---|---|
| `refuse` | auto, dontAsk | The call is refused, and the reason carries the fixed command. The model reruns it, and the auto-mode classifier judges it |
| `ask` | default, acceptEdits, plan | You see the fixed command and approve it |
| `allow` | bypassPermissions | It runs at once, and no classifier sees it |

**The time budget:** past 300 ms, the checks that start a subprocess are skipped. Past 2 s, every remaining check is
skipped and the call goes ahead. Both are settings.

**The Bash budget, on Windows:** a Bash command longer than 6,000 bytes, each apostrophe counted as four, gets
its heredoc or `python -c` body moved into a file, or is refused when there is no body to move. The Bash tool
cuts commands near 7,800 bytes. The setting is `transport.budget_bytes`, and a project file may lower it.

**Shell defaults:** at session start, io-guard gives every later Bash call `PYTHONUTF8=1` and
`PYTHONIOENCODING=utf-8`, so a Python print of a non-ASCII character works through a cp1252 console. On Windows
it adds `DOTNET_CLI_UI_LANGUAGE=en` and `VSLANG=1033`, so build tools report in English. The lists are the settings
`checks.session.probe.env` and `checks.session.probe.env_windows`, and only your own `config.json` can change them,
because a variable such as `PYTHONSTARTUP` can run a program.

**Your build command:** a build or test piped into `tail`, `grep` or `head` reports the filter's exit code, so
io-guard warns before it runs. It knows common builds such as `make`, `npm test` and `pytest`. To name your own,
list each by its first words in `checks.shell.lint.build_commands`, in your project's `.claude/io-guard.json`.
Your list replaces the default one.

**Recommended Claude Code settings**, proposed until the release confirms them:

```json
{
  "bashEditDiffEnabled": true,
  "env": { "ENABLE_TOOL_SEARCH": "auto:5" },
  "permissions": {
    "allow": ["mcp__plugin_io-guard_io__io_read", "mcp__plugin_io-guard_io__io_status", "mcp__plugin_io-guard_io__io_read_log"]
  }
}
```

## Work on it

The repository is also the plugin's marketplace. The shipped plugin is `plugins/io-guard/`, and nothing else ships.

```
plugins/io-guard/     the plugin: manifest, hooks, the io server, the skill
tests/                the unittest suite and the byte fixtures
tools/                corpus, replay, report and measure scripts, and the harness probes
docs/                 the architecture drawing, the design and its review, and the harness pages
.claude/tasks/        the build plan: one file per task, in build order
```

- Start with [`.claude/tasks/README.md`](.claude/tasks/README.md), then `context.md` beside it, then the design.
- Run the tests with `python -m unittest discover -s tests -t .`.
- After a Claude Code update, run `python tools/probes/run_probe.py run all`, then `verdicts`, to recheck every
  harness fact io-guard relies on. [`docs/compat.md`](docs/compat.md) lists the features, and
  [`docs/live-checks.md`](docs/live-checks.md) says when each was last confirmed.
- The author's own working rules and skills are linked in from a private kit and are not part of this repository. A
  release copies a snapshot of them into `docs/kit-snapshot/`.

## License

MIT. See [LICENSE](LICENSE).
