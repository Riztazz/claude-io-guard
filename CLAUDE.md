# claude-io-guard

io-guard is a Claude Code plugin that checks what an agent sends to the file and shell tools, fixes what it safely
can, and returns a structured error for the rest. One codebase runs on Windows and macOS. This repository is also the
plugin's marketplace: github.com/Riztazz/claude-io-guard.

## Layout

The tasks build most of this. Today the marketplace, the plugin's manifest, hooks, launcher, stub server and
stub skill, `tests/` with its fixtures and helpers, `tools/probes/`, `.github/workflows/ci.yml`, `.claude/`,
`docs/`, `workbench/` and this file exist.

```
.claude-plugin/marketplace.json   the catalog
plugins/io-guard/                 the shipped plugin: manifest, hooks, scripts/ioguard, skills, .mcp.json, ui
tests/                            the unittest suite, the byte fixtures, and support/ with the event builders
.github/workflows/ci.yml          the tests on Windows and macOS runners, Python 3.14 and the newest release
tools/                            corpus, replay, report, measure, the ioguard command line, and probes/
tools/probes/                     the harness probes: run_probe.py and the one-off plugin it builds per probe
workbench/                        copies of the lead's project files to test on, local and gitignored
docs/design/architecture.md       the design every task builds from, with every contract
docs/design/review.md             Fable's review of the plan, and the lead's answers
docs/architecture.svg             the architecture drawn, interactive on GitHub Pages or served from localhost
docs/compat.md                    each Claude Code feature io-guard uses, the version, the probe, the fallback
docs/live-checks.md               each live fact, with the platform, the version and the date last confirmed
docs/launcher.md                  how io-guard starts Python on each platform, and what each hook path costs
.claude/tasks/                    the build plan: README.md, context.md, open/, done/, baseline/
.claude/rules/this-repo.md        the rules for this repository
.claude/rules/docs.md             which doc each kind of change must update, the drawing included
.claude/skills/io-guard-dev/      how code here is laid out, written, tested and verified
```

## The kit's links

The lead's shared kit, UNREAL-SHARED, links its generic group in here with `install.ps1 -Profile generic`:

- `.claude/rules/shared/`: the always-on rules for every project
- `.claude/skills/engineering`, `testing`, `verification` and `prose`: the skills for every project
- `.claude/tools/shared/`: the kit's scripts, for the two hooks in `.claude/settings.local.json` that print the
  steps after a compaction and refuse shell writes

Claude Code loads a rule only when its real path is inside the project, and a linked rule's real path is the kit. The
installer therefore approves imports from outside the project for this folder, in the lead's `~/.claude.json`. With
that approval gone, the seven shared rules silently stop loading.

Every link is gitignored, and a public clone has none of them. **Never edit a linked file here**, and never add
one to git: git writes through a tracked link into the kit. A change to them is a task in the kit's `tasks/open/`.

## Start here

1. Read `.claude/tasks/README.md`, `.claude/tasks/context.md` and `docs/design/architecture.md`.
2. Pick the lowest-numbered open task whose `depends-on` tasks are all done.
3. Read the skills the task needs:
   - `io-guard-dev` before any work here
   - `engineering` before writing code
   - `testing` before writing a test
   - `verification` before handing work back
   - `prose` before any comment, docstring, message or page

## Running things

Each line works once the task that builds it has landed.

- Tests: `python -m unittest discover -s tests -t .`. CI runs `python tests/run_all.py`, the same suite, which
  also fails when no test ran
- Fixtures: `python -m tests.support.fixtures` rewrites the generated fixtures and `tests/fixtures/MANIFEST.sha256`
- The checks on one command, offline: `python tools/ioguard.py check "<command>"`
- The plugin for one CLI session: `claude --plugin-dir plugins/io-guard`
- The drawing, served for the browser pane: the `docs` entry in `.claude/launch.json`, at
  `http://127.0.0.1:8765/architecture.svg`
- The harness facts, after a Claude Code update: `python tools/probes/run_probe.py run all`, then
  `python tools/probes/run_probe.py verdicts`. `IOPROBE_CLAUDE` points it at the desktop app's own `claude.exe`
- The plugin in the desktop app, which is the lead's main surface: run
  `claude plugin marketplace add <path to this clone>`, then `claude plugin install io-guard@claude-io-guard`

# Compact instructions

Claude Code reads this section when it compacts a session here. Write the summary for the session that goes on
after it. That session knows only what the summary carries, this file, `.claude/rules/`, and what the kit's
after-compact hook prints.

Keep:

- **The recent context, close to word for word.** The lead's last requests and answers in the lead's own words, and
  the last things you reported.
- **The task in progress:** its file, its phase, and what was under way.
- **What no file holds yet:** a choice the lead made, a thing promised and not done, and the last test result with
  its numbers. A commit or push grant never carries over.
- **Errors and refusals, word for word.**

Name a skill and never summarise it. It is read again from disk after the compaction.

End the summary with this section:

```
Resume
Task: <the task file's path, or none>
Phase: <one line>
Files: <every file to re-read, by path, the task file first>
Skills: <every skill the task needs, by name>
Waiting on the lead: <each open question and grant, or nothing>
```
