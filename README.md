# io-guard

A Claude Code plugin that checks what an agent sends to the file and shell tools, fixes what it safely can, and
returns a structured error for the rest. One codebase runs on Windows and macOS.

**Status: in build.** The plugin installs, its io server runs the hooks and every io tool, and its hooks answer
every file and shell call. Twenty-one checks run so far: the session probe, where a write lands,
what holds a locked file, the Bash body move, the shell-write refusal, the quoting and dialect lint, the Git Bash
path fix, the endings and BOM fix for Write, the indent fix for Edit and the refusal of one that would join two
words, the check of each written file against the file before it, your own verify command after a write, the
files a shell command changed, the profile line after a Read, the diagnosis of a failed file call, both after it
fails and after Claude Code refuses it, what a shell command's result means, a warning when the io server is not
running, your permission rules on `io.run`, your commit policy, the question before `io.restore` overwrites your
edits, and the journal of every write. The
build plan is in `.claude/tasks/`, and this page describes the plugin the plan builds.

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
           changed, and the model reads EOL_CONVERTED: io-guard wrote the content with CRLF line endings, a
           BOM, and a final newline, as settings.ini has them.
```

**An Edit that misses.** The text the model sends is not quite the text in the file.

```
The call   Edit: client.py, old_string "    retries = 3"
Without    String to replace not found in file.
With       Claude Code refuses the Edit before any hook runs, so the answer comes with the model's next call:
           ANCHOR_NOT_FOUND: old_string of the refused Edit matches line 48 of client.py once spaces and
           tabs are ignored. client.py uses LF line endings. The file reads:
           48| [TAB]retries = 3
           Call Edit again with old_string "\tretries = 3".
```

**A write through the shell.** No check sees it, and rewind can't undo it.

```
The call   Bash: sed -i 's/timeout=30/timeout=60/' src/client.py
Without    The file changes, and nothing records how.
With       Refused. SHELL_WRITE: This command writes C:/work/app/src/client.py, which git tracks, through
           sed -i, so the write skips io-guard's byte checks and Claude Code's checkpoints. Use the Edit tool
           to change it, or the Write tool to replace it whole.
```

**A search that finds nothing, inside a chain.** grep exits with 1 when no line matches, and `&&` stops there.

```
The call   Bash: grep -q "legacy_api" src/client.py && echo still used
Without    Exit code 1, and the model reports that the command failed.
With       EXIT_BENIGN: Exit code 1 is the answer grep gives when no line matches, not a failure. The
           commands after it in the && chain did not run. Join them with ; instead of &&, or put || true
           after grep, when that answer is expected.
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
| Write turns a CRLF file into LF and drops its BOM, and an Edit's new text comes indented with spaces in a file indented with tabs, or the other way round | 328 "LF will be replaced by CRLF" warnings | Rewrites Write content in the file's own endings, BOM and final newline, and an Edit's new text in the indent of the lines around it, before either runs. A new file takes its endings from `.editorconfig`, `.gitattributes` or the files beside it |
| A write leaves damage no tool reports: letters a code page lost as U+FFFD, control bytes, lines changed outside the edit, a file cut short | Never reported, so the transcripts can't count it | Compares each written file with the file before it, puts back a lost BOM or line endings, and names the rest with its lines. An optional git pre-commit hook checks the staged files the same way |
| An Edit fails with EPERM because a program holds the file, or a write hits a read-only file | 3 EPERM failures | Names the program and its process id after the failure. Refuses a read-only file before the write, with `git lfs lock` when the file is lockable |
| A formatter or a script changes a file the model has read, or rewrites its endings, and nothing says so | 30 "modified since read" failures | After each shell command, names the files it changed, created or deleted, tells the model to read the changed ones again, and names what it did to their endings or BOM |
| Read shows a CRLF file, an LF file and a file with a BOM the same way | Agents ran a script of their own 107 times to find out | Adds one line after each Read, such as `io-guard: CRLF, BOM, UTF-8, tabs, 1,284 lines`, and a warning for mixed endings, invalid UTF-8, NUL or private-use bytes |
| A failed Edit says "not found" and nothing else, and a failed Read, Grep or Glob names the problem but not the fix | 67 anchor misses, 112 stale reads, 175 missing paths | With the model's next call, returns the closest match, the file's endings and a corrected call. After a failed Read, Grep or Glob, names the paths that exist, the parts of a file that fit, or a pattern ripgrep accepts |
| `sed -i`, redirects and scripts write files around the edit tools, so no check and no rewind sees them | 2,876 shell writes | Refuses a write to a file git tracks, names the tool that does it safely, and warns about a script created inside the repository |
| Bash reads a command differently from what was meant: a Windows path's last backslash escapes its quote, a backtick inside double quotes runs as a command, PowerShell syntax goes to the Bash tool, a Python body doesn't compile | 29 failed commands, and 11 more that ran and did the wrong thing | Rewrites the path with forward slashes, and refuses the rest with the fix |
| On Windows, Git Bash turns an argument such as `/Name/X` or `/F` into a path before a Windows program sees it, and `2>nul` writes a file named `nul` | 17 results show a converted path, 163 commands pass such an argument, 3 redirect to `nul` | Names those arguments in `MSYS2_ARG_CONV_EXCL`, and writes `cmd //c` and `/dev/null` |
| A long output is saved to a file the model reads again, grep's exit code 1 stops a chain, a pipe into `tail` hides a failure, and a console loses characters as U+FFFD | 147 saved outputs, 870 failures with exit code 1, 562 outputs that report an error behind exit code 0, 59 outputs with U+FFFD | Shows a saved output's first and last 20 lines and its error lines in its place, labels an exit code that is an answer, names the errors a pipe hid, and gives the encoding fix |

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
5. **After the call, the result is checked too:** the bytes on disk against the file before the call, with a lost
   BOM or line endings put back, the files a shell command touched, and the errors in the output.

Every disk read and write goes through one library, `lib`, so the same code protects the hooks, the io tools and the
tests.

### The io tools

A few jobs have no safe built-in tool, so the io server adds them:

| Tool | Job |
|---|---|
| `io.read` | A file's lines exactly as the file holds them, after its line endings, BOM, encoding and indent |
| `io.edit` | Several edits in one file, all or nothing, in the file's own endings, BOM and encoding |
| `io.splice` | Replace the text between a unique start marker and the end marker after it |
| `io.append` | Add lines to the end of a file, dated if you ask, wrapped at the file's `.editorconfig` column |
| `io.run` | Run a program from an argument list, or a script body byte for byte, with no shell in between, under your Bash and PowerShell rules |
| `io.status` | Whether a background `io.run` still runs, from the process itself, and how it ended |
| `io.read_log` | The whole lines a log gained since the last read, less your noise patterns |
| `io.format` | Run your formatter, clang-format by default, over the lines changed since the last commit and no others |
| `io.snapshot` | Keep the bytes of files, folders or globs under a tag for seven days, before a pass over many files |
| `io.restore` | Put back the files a snapshot kept, only those that changed, after your yes |
| `io.compare` | Show whether a pass changed code since a snapshot, ignoring comments or include lines, and where |
| `io.stage` | Stage the hunks of a file that meet the lines you name, or that one task wrote, and never commit |

The three that change a file write it once, only when every place they name matched once, and a failed one
writes nothing and names the lines it nearly matched. Two subagents editing one file take turns. After one of
them changes a file, the built-in Edit tool needs a fresh Read of it, and every result says so.

`io.format` hands the formatter only the lines `git diff` says changed, or the whole file when git has no
commit of it, or the lines the call names. The file keeps its line endings and BOM whatever the formatter's
config says, and a change the formatter makes away from those lines, such as a `// namespace` closer at the
end of the file, stays out. When the formatter fails on one file, no file is written.

`io.run` meets your deny and ask rules for Bash and PowerShell, from every settings file Claude Code reads. A
deny rule refuses the run, and an ask rule brings up Claude Code's own permission prompt. A background run's
handle lasts an hour past the program's end.

`io.snapshot` keeps its copies in io-guard's folder, up to 5,000 files and 512 MB each, and deletes them after
seven days. `io.restore` undoes a task file by file, where `git checkout` would throw away every other edit
of the file too. It writes back only the files that changed since the snapshot, and Claude Code's own
permission prompt asks you first, naming the files whose edits you'd lose.

`io.stage` splits a session's work into commits without `git add -p`. Give it lines, or the tag you gave
`io.snapshot` before a task, and it stages the hunks the journal says that task wrote. A hunk holding
two tasks' lines is left for you, and named.

## What it never does

- **It never disables a built-in tool.** A tool Claude Code can't see is a tool the model routes around.
- **It adds no escaping layer.** Content travels as a tool argument or in a file, never inside a shell string io-guard
  builds.
- **It never fixes silently.** Every fix is reported to the model, and a fix that could change meaning is a refusal
  with the corrected call instead.
- **It never blocks your work because of its own bug.** A check that crashes is skipped and logged, and you get one
  warning per session.
- **Nothing leaves your machine.** Its telemetry holds codes and timings, never file content, and it stays in
  io-guard's folder, `~/.claude/io-guard`.

## Install it

Once the first release is out:

1. In claude.ai, open Customize > Plugins and add `Riztazz/claude-io-guard`. Or, in Claude Code, run
   `/plugin marketplace add Riztazz/claude-io-guard`, then `/plugin install io-guard@claude-io-guard`.
2. You need Claude Code 2.1.281 or later and Python 3.14 or later, and on Windows, Git for Windows.
   [`docs/compat.md`](docs/compat.md) says why 2.1.281, and what io-guard does when a Claude Code feature it
   uses is missing.
3. There's nothing to set. io-guard finds Python itself: `py -3`, then `python` on Windows, and `python3`, then
   `python` on macOS. When yours is somewhere else, set `IOGUARD_PYTHON` to its full path in the `env` block of
   `~/.claude/settings.json`. [`docs/launcher.md`](docs/launcher.md) has the details, and what you see when no
   Python 3.14 is found.

When the io server stops, your tool calls still run, unchecked, and io-guard says so once at the start of your
next turn. Claude Code starts a stopped server again at the next tool call. When one fails to start, Claude Code
skips it in every session for the next 15 minutes, and io-guard names that too. `/mcp` shows why it failed.

Until 1.0, installs follow the latest commit. From 1.0 on, releases are tagged.

## Configure it

Every setting has a default, and every default is a setting. Your settings live in `config.json` in io-guard's
folder, and a project can add `.claude/io-guard.json`. A project file can only make io-guard stricter: it can't
approve commands or make io-guard run a program.

io-guard's folder is `~/.claude/io-guard`, or `io-guard` inside `CLAUDE_CONFIG_DIR` when you've moved `~/.claude`,
or wherever `IOGUARD_HOME` points. It holds your `config.json`, the file locks that keep two sessions from
writing one file at once, the telemetry, each session's heartbeat, the snapshots, and the edit journal:
one line per write naming the file, the lines it changed, the tool and the task, with each line kept as a
hash and never as text. Every copy of the plugin shares it: the
desktop app, the terminal, and an install from claude.ai or from a marketplace. Uninstalling the plugin leaves
the folder, so delete it yourself to remove everything.

**What happens to a rewritten command** is yours to choose, per permission mode:

| Mode | Default | What you see |
|---|---|---|
| `refuse` | auto, dontAsk | The call is refused, and the reason carries the fixed command. The model reruns it, and the auto-mode classifier judges it |
| `ask` | default, acceptEdits, plan | You see the fixed command and approve it |
| `allow` | bypassPermissions | It runs at once, and no classifier sees it |

A Write or an Edit that io-guard fits to the file's endings, BOM and indent isn't a rewritten command. Claude Code
asks about it or approves it as it would have anyway, and a prompt shows the input as it will land.

**The time budget:** past 300 ms, the checks that start a subprocess are skipped. Past 2 s, every remaining check is
skipped and the call goes ahead. Both are settings.

**The Bash budget, on Windows:** a Bash command longer than 6,000 bytes, each apostrophe counted as four, gets
its heredoc or `python -c` body moved into a file, or is refused when there is no body to move. The Bash tool
cuts commands near 7,800 bytes. The setting is `transport.budget_bytes`, and a project file may lower it. When
a well-formed command over 5,000 bytes still fails with "unexpected EOF", your machine's Bash tool cuts sooner,
so io-guard holds the rest of the session's commands below that command's length, on macOS too.

**On a Mac:** a Bash command that uses bash 4 syntax, such as `readarray` or `${name,,}`, gets a warning when
your `bash` is macOS's 3.2, and one that gives a GNU-only option, such as `sed -i` with no suffix or `grep -P`,
gets one whatever bash runs it, because the tools are BSD's. The warning names the form both read.

**Shell defaults:** at session start, io-guard gives every later Bash call `PYTHONUTF8=1` and
`PYTHONIOENCODING=utf-8`, so a Python print of a non-ASCII character works through a cp1252 console. On Windows
it adds `DOTNET_CLI_UI_LANGUAGE=en` and `VSLANG=1033`, so build tools report in English. The lists are the settings
`checks.session.probe.env` and `checks.session.probe.env_windows`, and only your own `config.json` can change them,
because a variable such as `PYTHONSTARTUP` can run a program.

**Your build command:** a build or test piped into `tail`, `grep` or `head` reports the filter's exit code, so
io-guard warns before it runs. It knows common builds such as `make`, `npm test` and `pytest`. To name your own,
list each by its first words in `checks.shell.lint.build_commands`, in your project's `.claude/io-guard.json`.
Your list replaces the default one.

**What a result means:** after each Bash and PowerShell call, io-guard labels an exit code that is an answer,
such as grep's 1 for no match, and quotes the lines that report errors. A project can add its own. In
`checks.shell.results.benign_exits`, map a command's first words to its answer codes, such as
`{"lint-check": {"3": "the files need formatting"}}`. In `checks.shell.results.error_patterns`, add a group of
regular expressions for its error lines, such as `{"log": ["^Log\\w+: Error: "]}`. A run of what a failed
build made gets a warning. `checks.shell.results.builds` and `runs` name those commands, and by default
`ctest` runs what `cmake --build` makes. `io.run` labels its results the same way.

**Log noise:** `io.read_log` leaves out the lines a regular expression in `noise_patterns` matches, such as
`["^LogTemp: Display:"]`. A project file's pattern in `noise_patterns` or `error_patterns` must compile, stay
under 200 characters, and never repeat a group that repeats inside it, such as `(a+)+`, because one such pattern
can stall on a single line of output. Your own `config.json` may set any pattern.

**Runs:** `io.run.timeout_s`, 120 by default, is how long a run to its end may take when the call names no
timeout. `io.run.handle_ttl_s` is how long a background run's handle lasts after the program ends, an hour.
`io.read_log.max_lines` caps one read of a log at 500 lines.

**After each write:** io-guard compares the file with the file before the call. A BOM or line endings the
write lost go back on, and the model is told to read the file again. Turn that off with
`checks.verify.write.repair`. To have non-ASCII flagged in some files, list their extensions in
`checks.verify.write.ascii_only`, such as `[".py", ".md"]`. It's empty by default. In every file, a write that
adds a character the Read tool shows as nothing, such as a U+FEFF where its escape was meant, a
zero-width space or a no-break space, gets a warning naming it and its line. List the ones a project uses on
purpose in `invisible_allowed`, such as `["U+00A0"]`.

**Trees a report leaves out:** after a shell command, io-guard names the files it changed. To leave out a tree
whose changes are noise, such as generated assets, list its glob in `skip_trees`, such as `["Content/**"]`. A
project file may set it.

**Your verify commands:** io-guard can run a command of yours on each file the model writes, and hand its output
to the model. Name them by extension in your own `config.json`, and add a project's own under its folder:

```json
{
  "verify": {
    ".py": ["python", "-m", "py_compile", "{file}"],
    "C:/work/app": {".js": ["node", "--check", "{file}"]}
  }
}
```

`{file}` becomes the file's path, and the command runs with no shell, stopped after 10 seconds. A project's
`.claude/io-guard.json` can't name one, because a repository you clone must not make io-guard run its programs.

**Your formatter:** `io.format` runs clang-format for C and C++ files by default, found on your `PATH`, with the
project's `.clang-format` and no style at all where the project has none. To use another clang-format, or to
format another language, name the command by extension in your own `config.json`, the same way as a verify
command. The command reads the file on stdin and prints the formatted text, and the argument that holds
`{first}` and `{last}` repeats once for each range of lines:

```json
{
  "format": {
    ".cpp": ["C:/Program Files/LLVM/bin/clang-format.exe", "--style=file", "--fallback-style=none",
             "--assume-filename={file}", "--lines={first}:{last}"],
    ".py": ["black", "-q", "--line-ranges={first}-{last}", "-"]
  }
}
```

Your entry for an extension replaces the default one. `io.format.timeout_s`, 30 by default, is how long the
formatter may take on one file.

**The pre-commit hook**, optional: it checks each staged file against its last commit, and stops a commit that
changes a file's line endings, BOM or indent, or adds control bytes, U+FFFD, or non-ASCII where
`ascii_only` names the file. Point your repository's `.git/hooks/pre-commit` at the script in the plugin's
folder, or in a clone of this repository:

```sh
#!/bin/sh
exec python "<plugin folder>/scripts/precommit.py"
```

`git commit --no-verify` skips it for one commit.

**Your commit policy:** list the texts no commit message may hold in `commit_policy.forbid`, such as
`["Co-Authored-By", "Generated with"]`, and set `commit_policy.ascii_only` to keep messages ASCII. io-guard then
refuses a `git commit` whose message breaks either, from Bash, PowerShell or `io.run`, and the model commits
again without it. It reads the message from `-m`, from a `-F` file or heredoc, and from a PowerShell
here-string. Both are off by default. `forbid` is yours alone, and a project file may only turn `ascii_only`
on.

**Commits and pushes you approve:** a plugin cannot ship permission rules, so add these to your own
`settings.json` to be asked before every commit and every push, auto mode included, and to never have
`git reset --hard` run:

```json
{
  "permissions": {
    "ask": ["Bash(git commit *)", "Bash(git push *)", "PowerShell(git commit *)", "PowerShell(git push *)"],
    "deny": ["Bash(git reset --hard *)", "PowerShell(git reset --hard *)"]
  }
}
```

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
tools/                corpus, replay, report, measure and skill scripts, and the harness probes
docs/                 the architecture drawing, the design and its review, and the harness pages
.claude/tasks/        the build plan: one file per task, in build order
```

- Start with [`.claude/tasks/README.md`](.claude/tasks/README.md), then `context.md` beside it, then the design.
- Run the tests with `python -m unittest discover -s tests -t .`.
- After adding a code or an io tool, run `python tools/skill.py` to write the skill's tables. A test fails until
  you do.
- See what io-guard fixed, warned about and refused this week with `python tools/report.py`. It reads the
  telemetry in io-guard's folder, and `--data` names another folder.
- Compare the failure classes before and after io-guard with `python tools/measure.py NAME=FOLDER ...`, one
  pair per transcript folder under `~/.claude/projects/`, and `--since` the day io-guard went on.
- After a Claude Code update, run `python tools/probes/run_probe.py run all`, then `verdicts`, to recheck every
  harness fact io-guard relies on. [`docs/compat.md`](docs/compat.md) lists the features, and
  [`docs/live-checks.md`](docs/live-checks.md) says when each was last confirmed.
- The author's own working rules and skills are linked in from a private kit and are not part of this repository. A
  release copies a snapshot of them into `docs/kit-snapshot/`.

## License

MIT. See [LICENSE](LICENSE).
