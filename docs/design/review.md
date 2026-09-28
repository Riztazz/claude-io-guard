# Review of the io-guard plan

Written on 2026-09-27 against `.claude/tasks/context.md`, the 35 open tasks, the rules, the skills and
`baseline/fable_review.md`. Every doc claim below was re-read today at code.claude.com/docs and
modelcontextprotocol.io. `architecture.md` beside this file holds the design the review points at.

## Check the four MCP conclusions

1. **Dual-era is right, and legacy is the production path.** The v2 runtime asks HTTP servers and claude.ai
   connectors for 2026-07-28. It connects stdio servers with `initialize` unless `MCP_PROTOCOL_NEGOTIATION` is
   `auto` (mcp.md, "MCP client runtimes"). The changelog records a fix that stopped Claude Code sending
   `server/discover` to stdio servers before `initialize`. So `server/discover`, per-request `_meta` and
   `input_required` reach the io server only when the lead sets that variable. Build the legacy path first.
2. **MCP Apps as an optional layer is right.** Claude Code hides `ui://` resources from `@` suggestions and
   resource lists, and documents no rendering. The Apps extension puts `_meta.ui.resourceUri` on the tool and
   `_meta.ui` on the resource, as task 35 has it. Its identifier is `io.modelcontextprotocol/ui`.
3. **Enterprise-Managed Authorization does not apply.** The basic spec says stdio implementations take
   credentials from the environment and do not follow the authorization spec.
4. **The stateless patterns fit, with four corrections.** `input_required` is modern-only, and Claude Code
   answers the legacy `elicitation/create` request since 2.1.76, with URL mode on 2026-07-28 connections since
   2.1.281, so the legacy elicitor is primary. Tasks are a separate extension,
   `io.modelcontextprotocol/tasks`, with no Claude client in the matrix, so handles come first. Progress and
   cancellation are unchanged: `progressToken` with `notifications/progress`, and `notifications/cancelled` on
   stdio. The TypeScript SDK client validates `structuredContent` against `outputSchema`, and a mismatch fails
   the call, so every output schema allows extra properties.

One check in `baseline/fable_review.md` is out of date. The hooks page today says `updatedInput` combines with
`allow` to auto-approve or with `ask` to show the modified input to the user. That changes the transport
design, which is hole 1.

## Rank the holes

1. **A rewrite is an approval.** `allow` skips the permission prompt. The classifier's decision order names
   rules, read-only actions and file edits, and the critical-path rule, which stops a hook `allow` from
   approving `rm -rf ~` "even in modes that skip other prompts", implies that a hook `allow` approves everything
   else. So every heredoc the guard moves into a file is a command the classifier never sees. Tasks 09, 11 and
   12 assume rewriting is free. The fix is a rewrite mode per permission mode. In `default`, `acceptEdits` and
   `plan`, answer `ask` with `updatedInput`, so the user sees the moved-body command where a prompt was due
   anyway. In `auto`, refuse with the corrected call by default, and let user config choose `ask` or `allow`.
   In `dontAsk` and headless runs, refuse. File-tool rewrites in task 15 are unaffected, because the harness
   auto-approves edits inside the working directory in auto mode.
2. **`io.run` bypasses the user's Bash rules.** Settings cannot match an MCP tool's parameters, so
   `Bash(curl *)` in deny or `Bash(git push *)` in ask never apply to `io.run(argv=["git", "push"])`. The fix
   is rule parity: `io.run` reads the user and project permission rules, matches its argv against the Bash and
   PowerShell deny and ask rules, refuses on deny and elicits on ask. Task 23 gains that.
3. **The launcher problem, and the one-process runtime.** Tasks 04, 05 and 21 each carry part of the
   interpreter question, and no interpreter name exists on both platforms. The docs list `${user_config.KEY}`
   substitution for MCP server config and exec-form hook `args`, and not for a hook's `command`. The
   `mcp_tool` hook path removes the problem: only the server starts Python, from `${user_config.python}`. The
   docs give string `${path}` substitution in `input`, the scoped name `plugin:io-guard:io`, a non-blocking
   error when the server is down, and since 2.1.281 a wait for the server on blocking events. They do not say
   what an absent field, a boolean or an object becomes, or whether a hook-invoked tool prompts. Task 03 item
   13 becomes the gate with those tests. SessionStart stays a command hook, because `CLAUDE_ENV_FILE` is a
   variable of a hook process.
4. **A crashed server ends guarding silently.** Claude Code does not reconnect stdio servers. The server
   needs a crash-proof dispatcher, a heartbeat file, a once-per-turn check that warns, and the `hook error`
   notice as the user's signal. Task 21 gains all four.
5. **Tool search hides the io tools, and manual mode prompts on each.** A refusal that says "use io.edit"
   sends the model to a tool it has not loaded. Every fix names the callable name and the ToolSearch step. The
   README carries `permissions.allow` for the read-only tools and `ENABLE_TOOL_SEARCH=auto:5`. Task 03 probes
   whether `readOnlyHint` changes the prompt.
6. **A post-write repair makes the next Edit stale.** The harness records a file's state after its own
   write. A repair in PostToolUse moves the mtime, so the next Edit fails with "modified since read". Conform
   before the write, repair after only where data would be lost, and always add "Read this file before the
   next Edit". Telemetry counts every repair.
7. **Rewrites that add words change rule matching.** A `set -o pipefail` prefix adds a subcommand that no
   narrow allow rule matches, and a leading `MSYS2_ARG_CONV_EXCL` assignment stops allow rules matching past
   it. `PIPE_HIDES_EXIT` warns only. The MSYS prefix goes through the rewrite mode of hole 1.
8. **`bashEditDiff` needs a user setting.** `bashEditDiffEnabled: true` counts only from user or managed
   settings. Task 19 makes the git snapshot primary, and the README snippet carries the setting.
9. **The dashboard puts telemetry into the model's context.** `io.dashboard` returns `structuredContent`, so
   command heads and paths land in the conversation. The tool returns counts and percentiles only.
10. **The transport budget is a guess per machine.** When PostToolUse sees "unexpected EOF while looking for
    matching" on a command over 5 KB, the guard records the failing length minus one as the session budget and
    names the cause. Tasks 08 and 20.
11. **Which bash runs on macOS is unknown.** Task 29's lint depends on it. Probe `bash --version` through the
    Bash tool on the Mac.
12. **Kit links and rewind.** Checkpoint restore skips symlinked paths, so linked rules edited on the Mac
    cannot be rewound. Junctions are unverified.

## Work with agents

- **Run task 03 before any check exists.** Every stage after it re-plans on its results.
- **One agent, one task, one file.** Tasks in dependency order, the subject proposed first, the lead commits.
  Two agents run in parallel only on tasks that share no file, such as 11 and 13.
- **Dogfood from task 04 on.** Install the plugin at user scope from the local marketplace and run
  `/reload-plugins` after each change. Keep every rewrite off by config until its replay is green.
- **Replay is the CI of policy.** A new rule ships with its replay numbers in the task's What changed section.
- **Build with the kit's guard on.** The agents building io-guard hit the traps it catches. Until task 10
  lands, the kit's `shell-write-guard.py` hook runs here through the generic profile of task 33.
- **Run checks from the shell, and record the Claude Code version with every live result.**
  `tools/ioguard.py check "<command>"` answers most questions offline, and the harness changes weekly.

## Modernise

- **Tests.** Six levels, each answering one question: `lib` with bytes, checks with a fake `Context`, the
  pipeline for ordering and the fixed point, hooks with JSON in and out, MCP conformance in both eras from
  recorded requests, and replay over the corpus. `architecture.md` section 11 has the layout and the meta
  tests that keep the suite honest.
- **Mechanism and policy.** `lib` holds no config, no session and no decision. A test that has to build a
  `Context` to reach a `lib` function has found a leak. Policy is the checks, the config and the tool contracts.
- **OOP for the checks.** Fifteen checks exist in the plan, so a base class, metadata, an explicit registry
  and a pipeline pay now under the two-bars rule. `lib` stays functions and frozen dataclasses.
- **Threads in the server, none in the hook path.** The server takes concurrent calls from parallel subagents,
  runs git and formatters, pumps background processes and writes telemetry. A reader thread, a worker pool, a
  writer lock, a telemetry queue and per-path locks cover that. The work is synchronous file IO, and threads
  suffice without a second concurrency model.
- **One long-lived process for hooks and tools.** Adopt it as the primary runtime, gated on task 03 item 13.
  A process spawn costs on the order of 100 ms per call and a round trip a few milliseconds, pending task 04's
  numbers, and the caches for profiles, git status and the read set are shared. The command entry point stays
  as the CLI and as the fallback. Holes 3 and 4 are the price.

## Judge the kit profile approach

The single source is right. Five consequences follow.

- A public clone has no rules and no skills. `CLAUDE.md` says where they come from, and CI never needs them.
- Rewind skips symlinked paths, so linked rules edited on the Mac need git to undo.
- `install.ps1` runs on the Mac only with `pwsh` installed, or it becomes Python like the kit's other tools.
  Profiles belong in a data file the installer reads, not in branches.
- The plugin never depends on the kit at run time. Its shipped skill is its own.
- The prose lint of task 34 enforces the prose skill, so it belongs in the kit's generic group beside it.

## Change the tasks

- **03:** add the `mcp_tool` substitution tests, `ask` with `updatedInput`, whether a hook `allow` skips the
  classifier in auto mode, whether a hook-invoked MCP tool prompts, whether `io.*` calls prompt in manual mode
  and whether `readOnlyHint` changes that, `bash --version` through the Bash tool on the Mac, and the
  `hook error` notice when the server is down.
- **04:** narrow it to the SessionStart launcher and the fallback. Measure `mcp_tool` hook latency against
  the command hook.
- **05:** split into 05a, the runtime core (`Event`, `Context`, `Decision`, `Pipeline`, `Registry`, budget,
  fixed point), and 05b, the hook entry point and the MCP bridge.
- **08:** add the adaptive budget. Keep SessionStart as a command hook.
- **09:** add the rewrite mode per permission mode. Default `ask` in prompting modes, refuse in auto.
- **11:** `PIPE_HIDES_EXIT` warns only. Drop the `set -o pipefail` prefix.
- **12:** the MSYS prefix follows the rewrite mode. Reserved names stay a refusal.
- **15:** skip the ANC-4 extension when `replace_all` is true.
- **16:** repair only data-loss classes, always add the re-read line, count repairs.
- **19:** git snapshot primary, `bashEditDiff` secondary, README snippet for the setting.
- **21:** add the hook bridge tools, the crash-proof dispatcher, the heartbeat, `${user_config.python}` in
  `.mcp.json`, loose output schemas, and the concurrency model.
- **23:** add Bash-rule parity for `io.run`. Move the Tasks extension to a later task.
- **27 and 35:** counts only in the tool result. Details in the page.
- **31:** add the settings snippet: `bashEditDiffEnabled`, `permissions.allow` for read-only io tools,
  `ENABLE_TOOL_SEARCH=auto:5`.
- **34:** the commit check parses `-F <file>` and PowerShell here-strings too.
- **Add 36:** the compatibility matrix and the live-check list, one page each, updated by every live task.
- **Drop nothing.** Task 25's hunk staging and task 35 move behind task 28 in the order.

## The lead's answers, 2026-09-27

The task numbers above are the ones before the renumbering. `.claude/tasks/README.md` maps them to the new ones,
and `.claude/tasks/context.md` records each answer as a decision. Task 03's item 13 above is item 12 in the
renumbered task 03, and its macOS items moved to task 36.

| Question | Answer | Decision |
|---|---|---|
| Rewrite mode in auto mode | A user setting. Refuse with the fix by default, ask as the second choice, allow silently as the third | D12 |
| The one-process runtime | One io server per session, shared by its subagents and thread-safe, with lock files across processes. Not a daemon per project, and not a process per call | D13 |
| `userConfig.python` default | `python3`. The lead sets `python` once on Windows, where `python3` is the Store stub | D15 |
| Hunk staging and the dashboard after the measurement | Yes, and every task in one linear order | D20 |
| Rule parity for `io.run` | Yes | D14 |
| The review's length | Kept whole, because the task list is what the handover needs | |
| Fail open (D7) | Confirmed | D7 |
| The Python floor | 3.14 | D15 |
| Line length | 110 | D17 |
| The time budget | 300 ms, a 2 s cap, configurable like every policy value | D16 |
| Versioning | Commits until 1.0, then tags | D18 |
| The kit's skills and rules | Linked and gitignored, with a snapshot copied in at each release | D11 |
| Publishing the catalog | Everything except the rows from a third-party scan | D19 |

One change to this review follows from D11: the kit's guard hook reaches this repository through the `generic`
profile's settings, written to `.claude/settings.local.json`, so nothing from the kit's tools is committed here.
