# io-guard

A Claude Code plugin that checks what an agent sends to the file and shell tools, fixes what it safely can, and
returns a structured error for the rest. One codebase runs on Windows and macOS.

**Status: in design.** The design is finished and the build plan is in `.claude/tasks/`, but no code ships yet. This
page describes the plugin the plan builds.

<a href="https://riztazz.github.io/claude-io-guard/architecture.svg"><img src="docs/architecture.svg" alt="io-guard's architecture: Claude Code's tools on top, the plugin's io server, checks and lib in the middle, and the files on disk at the bottom, with four numbered flows" width="100%"></a>

GitHub shows the drawing as a still image. **[Open the interactive drawing](https://riztazz.github.io/claude-io-guard/architecture.svg)**
to follow each flow step by step, and hover a box to see what it does. The full design is
[`docs/design/architecture.md`](docs/design/architecture.md).

## What it fixes

The numbers come from 738 transcripts of real agent sessions, 2026-06-20 to 2026-09-27.

| What goes wrong | How often | What io-guard does |
|---|---|---|
| On Windows, a Bash command longer than about 7.8 KB fails with "unexpected EOF", and every `\\` loses a backslash | 241 failed commands, about 531k tokens | Moves the script body into a file and runs the file |
| Write turns a CRLF file into LF and drops its BOM, and Edit trims trailing spaces from the new text | 432 "LF will be replaced by CRLF" warnings | Rewrites the input in the file's own endings, BOM and indent before it runs |
| A failed Edit says "not found" and nothing else | 71 anchor misses, 137 stale reads | Returns the closest match, the file's endings and a corrected call |
| `sed -i`, redirects and scripts write files around the edit tools, so no check and no rewind sees them | 6,217 shell writes | Refuses the write and names the tool that does it safely |
| Long output is cut, and exit code 1 from grep stops a chain | 180 cut results | Labels the exit code and summarises the errors |

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
   `python`. The default is `python3`, which on Windows is often the Microsoft Store stub.

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
