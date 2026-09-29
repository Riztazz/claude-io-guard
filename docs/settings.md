# io-guard's settings

Every setting has a default, and every default is a setting. This page lists them all. The
[README](../README.md) says what io-guard does.

## Where settings live

Your settings live in `config.json` in io-guard's folder, for every project. A project can add
`.claude/io-guard.json`, and anything in it overrides yours for that project, so a repository that ships one
works as it is from the first session. It holds for the whole project, from any subfolder a session works in,
and for the project's files only: a file outside it gets your settings alone. A project's list replaces yours.

Some settings stay yours alone, because they reach every project: `telemetry.retention_days`,
`telemetry.cmd_head_days`, `io.saved_days`, `io.server.workers`, and the variables the session probe exports,
`checks.session.probe.env` and `env_windows`. The rewrite modes, `transport.rewrite_mode.*`, stay yours too,
because `allow` approves a command in Claude Code's place. When a project's file changes any of your other
settings, io-guard tells you once a session, naming each one beside your own value.

**A project's commands wait for your yes.** `verify` and `format` name programs io-guard starts, and any
repository you clone can ship a `.claude/io-guard.json`. So a project's commands don't run until you approve
them. io-guard tells Claude once a session, Claude calls `io.trust`, and Claude Code's own permission prompt
shows you each command. Say yes and they run from the next tool call. io-guard keeps the approval in
`trust.json` in its folder, tied to those exact commands, so a pull that changes one asks again. A command that
runs a script from inside the repository gets a warning in the prompt, since a pull can change the script
without changing the command.

## Change a setting

**Ask Claude**, such as "turn off shell.lint for this project". `io.config` writes it into your file or the
project's, checked the way io-guard checks the whole file, so a value the file couldn't load is refused and
nothing is written. A change applies from the next tool call. A command or a variable for every project,
`verify`, `format` or the session's Bash variables in your own file, waits for your yes in Claude Code's
permission prompt, and the settings page leaves those to `io.config`.

**Open the settings page** to see every setting at once: pick `settings` under io-guard in the plugin menu, type
`/io-guard:settings`, or ask Claude to open io-guard's settings page. `io.dashboard` serves it on `127.0.0.1`, on
this machine only and behind a token in its URL, and Claude opens it in the desktop app's browser pane. Once
the page loads, the token leaves the address bar and the browser's history. Claude also gives you a link, Open
io-guard's settings page, which opens the same page in any browser on this machine. Each setting shows a line
of help and a tooltip with its key and default, then two columns: All projects, from your `config.json`, and
Only this project, from the project's `.claude/io-guard.json`. The project's column shows your value, greyed,
until you press Change for this project, and Use all projects' value undoes that. A change saves at once
through `io.config`, and the file comes back two-space formatted. The page's server stops five minutes after
you close the page, or after `io.dashboard.idle_minutes`, and asking again opens a new one.

## See what it did

The settings page's Stats switch shows what io-guard fixed, warned about and refused over the last 1, 7 or 30
days, for this project or for all of them: a bar per day, every code with its counts, and the time each call
took. Click a code to see what it means, how to fix it, and its last 20 lines with the command behind each. The
stats come from the telemetry in io-guard's folder and never leave your machine.

To reset the stats, press Start from now: the page counts only what happens after it, and Show everything
brings the rest back. Nothing is deleted. Delete all... deletes every project's telemetry after two
confirmations, and it can't be undone.

## What io-guard keeps, and for how long

io-guard's folder is `~/.claude/io-guard`, or `io-guard` inside `CLAUDE_CONFIG_DIR` when you've moved `~/.claude`,
or wherever `IOGUARD_HOME` points. It holds your `config.json`, the file locks that keep two sessions from
writing one file at once, the telemetry, each session's heartbeat, the snapshots, and the edit journal: one line
per write naming the file, the lines it changed, the tool and the task, with each line kept as a hash and never
as text. Every copy of the plugin shares it: the desktop app, the terminal, and an install from claude.ai or
from a marketplace. Uninstalling the plugin leaves the folder, so delete it yourself to remove everything.

io-guard deletes a session's telemetry 90 days after its last line, or after `telemetry.retention_days` in your
config, and 0 keeps it all. The tool results, `io.run` bodies and logs, and moved command bodies io-guard saves
in its folder hold your projects' content, so it deletes them 7 days after their last change, or after
`io.saved_days`, and 0 keeps them. Telemetry keeps the first 200 characters of each command for the stats page,
and 7 days after a session's last line, or after `telemetry.cmd_head_days`, only the command's program name
stays.

## Every setting

**What happens to a fixed command** is yours to choose, per permission mode:

| Mode | Default | What you see |
|---|---|---|
| `refuse` | auto, dontAsk | The call is refused, and the reason carries the fixed command. The agent reruns it, and the auto-mode classifier judges it |
| `ask` | default, acceptEdits, plan | You see the fixed command and approve it |
| `allow` | bypassPermissions | It runs at once, and no classifier sees it |

A permission mode io-guard doesn't know yet, from a newer Claude Code, gets default mode's setting, and io-guard
tells you once a session.

A Write or an Edit that io-guard fits to the file's endings, BOM and indent isn't a fixed command. Claude Code
asks about it or approves it as it would have anyway, and a prompt shows the input as it will land.

**The time budget:** past 300 ms, the checks that start a subprocess are skipped. Past 2 s, every remaining check is
skipped and the call goes ahead. Both are settings.

**The io server's threads:** each session's io server runs tool calls and hooks on 4 threads, or on
`io.server.workers` from your own config, read when a session starts. At 1, a long `io.run` holds back every
hook until it ends.

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
under 200 characters, never repeat a group that repeats or chooses inside it, such as `(a+)+` or `(a|aa)+`,
and hold at most two open repeats such as `.*` or `\d+`, because one such pattern can stall on a single line
of output. Your own `config.json` may set any pattern.

**Runs:** `io.run.timeout_s`, 120 by default, is how long a run to its end may take when the call names no
timeout. `io.run.handle_ttl_s` is how long a background run's handle lasts after the program ends, an hour.
`io.read_log.max_lines` caps one read of a log at 500 lines.

**After each write:** io-guard compares the file with the file before the call. A BOM or line endings the
write lost go back on, and the agent is told to read the file again. Turn that off with
`checks.verify.write.repair`. To have non-ASCII flagged in some files, list their extensions in
`checks.verify.write.ascii_only`, such as `[".py", ".md"]`, or whole file names, such as `LICENSE` or
`.gitignore`. It's empty by default. In every file, a write that adds a character the Read tool shows as
nothing, such as a U+FEFF where its escape was meant, a zero-width space or a no-break space, gets a warning
naming it and its line. List the ones a project uses on purpose in `invisible_allowed`, such as `["U+00A0"]`.

**Folders a report leaves out:** after a shell command, io-guard names the files it changed. To leave out a
folder whose changes are noise, such as generated assets, list its glob in `skip_trees`, such as
`["Content/**"]`. A project file may set it.

**Your verify commands:** io-guard can run a command of yours on each file the agent writes, and hand its output
to the agent. Name them by extension in your own `config.json`, and add a project's own under its folder:

```json
{
  "verify": {
    ".py": ["python", "-m", "py_compile", "{file}"],
    "C:/work/app": {".js": ["node", "--check", "{file}"]}
  }
}
```

`{file}` becomes the file's path, and the command runs with no shell, stopped after 10 seconds. The program is
a bare name io-guard finds on `PATH` or an absolute path, since a relative one would run from whatever folder
the session is in. A project's `.claude/io-guard.json` can name commands too, and they wait for your yes, as
"Where settings live" says.

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
refuses a `git commit` whose message breaks either, from Bash, PowerShell or `io.run`, and the agent commits
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

**Recommended Claude Code settings:**

```json
{
  "bashEditDiffEnabled": true,
  "env": { "ENABLE_TOOL_SEARCH": "auto:5" },
  "permissions": {
    "allow": ["mcp__plugin_io-guard_io__io_read", "mcp__plugin_io-guard_io__io_status", "mcp__plugin_io-guard_io__io_read_log"]
  }
}
```
