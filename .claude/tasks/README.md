# Tasks

The build plan for **io-guard**, a Claude Code plugin that checks what an agent sends to the file and shell tools,
fixes what it safely can, and returns a structured error for the rest. It runs on Windows and macOS from one
codebase. The plan goes from an empty repository to a plugin hosted on GitHub and installed from claude.ai.

```
.claude/tasks/open/        waiting for someone
.claude/tasks/done/        finished, kept for the record
.claude/tasks/context.md   the evidence every task rests on: decisions D1 to D27, verified facts, doc facts,
                           baseline numbers, the failure catalog ids
.claude/tasks/baseline/    the measurement scripts and research notes behind the baseline of 2026-09-27
docs/design/               the architecture every task builds from, and the review it answers
```

**Read `context.md` and `docs/design/architecture.md` before your first task.** Every task cites failure ids such as
`SHW-4` or `BYT-1`. They are listed in `context.md`, and the full catalog with evidence is
`baseline/io_traps.html`.

## Build order

Files are named `NN-verb-subject.md`, and the number is the build order. Every `depends-on` entry is a lower number,
so taking the lowest open task whose dependencies are done never goes backwards (D20).

| Stage | Tasks | What it delivers |
|---|---|---|
| A. Foundations | 01-09 | Repo files, the plugin skeleton, the harness facts verified and tracked, tests and CI, the launcher, the runtime core, the hook entry point and bridge, the replay corpus |
| B. Transport | 10-14 | Nothing an agent writes is mangled or cut on its way into a shell, under the user's rewrite mode |
| C. Bytes | 15-19 | No write changes a file's endings, BOM, encoding or unrelated lines, and no write lands where it must not |
| D. Stale view | 20-21 | A failed edit returns the fix, and the agent learns which files a command changed |
| E. Output | 22 | Exit codes and errors come back structured, long output comes back summarised, and the transport budget learns |
| F. MCP server | 23-26 | The dual-era io server that runs the hooks and the tools: batch edit, splice, append, run, format hunks |
| G. Ship | 27-31 | The skill, the report, the workflow mechanisms, adoption in the projects, and the measured result |
| H. After the measurement | 32-33 | Snapshots and hunk staging, and the dashboard MCP App |
| I. Release | 34-36 | Publishing, the upstream report, and the macOS hardening that waits for the lead's Mac |

`done/00` is the handover's own task: the kit's generic group linked in, and this repository's own rules kept.

## The numbers before 2026-09-27

`baseline/fable_review.md` and `docs/design/review.md` use the old numbers.

| Old | New | Old | New | Old | New |
|---|---|---|---|---|---|
| 01 | 01 | 13 | 15 | 25 | 32 |
| 02 | 02 | 14 | 16 | 26 | 27 |
| 03 | 03 | 15 | 17 | 27 | 28 |
| 04 | 06 | 16 | 18 | 28 | 31 |
| 05 | 07 and 08 | 17 | 19 | 29 | 36 |
| 06 | 05 | 18 | 20 | 30 | 30 |
| 07 | 09 | 19 | 21 | 31 | 34 |
| 08 | 10 | 20 | 22 | 32 | 35 |
| 09 | 11 | 21 | 23 | 33 | done/00 |
| 10 | 12 | 22 | 24 | 34 | 29 |
| 11 | 13 | 23 | 25 | 35 | 33 |
| 12 | 14 | 24 | 26 | Fable's 36 | 04 |

## The file

```markdown
---
title: Route command bodies through files
stage: B
area: transport          # infra | runtime | transport | bytes | stale | output | mcp | docs | release
created: 2026-09-27
status: open             # open | claimed | done
depends-on: [03, 08, 09, 10]
findings: [SHW-2, SHW-4] # ids from context.md
platforms: [windows, macos]
commit: "feat: move heredoc and inline-script bodies into files before they run"
---

## Why
## What to build
## Where
## Done when
## Notes
```

`commit` is the proposed subject. The lead decides the final message.

## Working one

1. **Claim it.** Set `status: claimed` and add `claimed-by:`. One file, one writer.
2. **Read** `context.md`, the architecture sections the task names, and the findings it cites.
3. **Do the work** on the paths the task names. `platforms` says where the code must work. CI proves both platforms
   on GitHub's runners. Live checks run on Windows only while the lead's Mac is down (D21): a macOS live check goes
   into task 36's list instead.
4. **Update the docs the change made wrong**, in the same change: the drawing, the design, the README and the rest
   that `.claude/rules/docs.md` lists.
5. **Finish it.** Set `status: done`, add `## What changed`: the files, the docs updated, the evidence,
   `Checked on <platform> on <date>`, the Claude Code version for a live check, and what was not checked. Move the
   file to `done/` with `git mv`.

A task you cannot finish goes back to `open` with a `## Blocked on` section. A task that turns out wrong is
rewritten or deleted, not worked around.

## Rules

The rules live in `.claude/rules/`: `this-repo.md` and `docs.md` here, and `shared/`, linked from the lead's kit.
Claude Code loads all of them at every start. The shared ones load only because the kit's installer approves imports
from outside the project (`context.md`, "Rules through a junction"). The skills in `.claude/skills/` hold the
detail: `io-guard-dev` for this repository, and `engineering`, `testing`, `verification` and `prose` from the kit.
