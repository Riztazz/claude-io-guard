# Harness compatibility

io-guard leans on Claude Code features that change from one release to the next. This page lists each one, the
Claude Code version it needs, the probe that confirms it, and what io-guard does when it's missing.
[`live-checks.md`](live-checks.md) says when each fact was last confirmed, and on which platform.

## Check a new Claude Code release

Run every probe, then read the verdicts:

```
python tools/probes/run_probe.py run all
python tools/probes/run_probe.py verdicts
```

Each probe starts a headless session with a one-off plugin, then prints `pass` or `FAIL` against the result
recorded in `.claude/tasks/context.md`, "Hooks and MCP". To test the desktop app's own copy, set `IOPROBE_CLAUDE`
to its `claude.exe`, which on Windows sits in `%APPDATA%\Claude\claude-code\<version>\`.

A `FAIL` means a row below changed. Update the row, what io-guard does without the feature, and the date in
`live-checks.md`, all in the same change.

## The minimum version is 2.1.281

io-guard needs Claude Code 2.1.281 or later. It's the oldest release every probe has passed on. On 2026-09-27
the desktop app's bundled 2.1.281 passed all 28 verdicts, and so did the CLI at 2.1.283. Task 08 added six
probes the same day. Five passed on both releases, and `guard-large`, which costs about 33,000 output tokens,
ran on 2.1.283 only. Task 17 added `write-quiet`, `edit-trailing` and `live-conform`, task 18
`live-verify` and `live-verify-direct`, task 19 `live-read-only` and `live-locked`, task 20 `edit-refusals`,
`other-refusals` and `live-diagnose`, task 21 `live-touched`, task 22 `command-output` and
`live-results`, task 23 `live-server`, `live-server-modern` and `live-server-down`, task 24
`live-edit-parallel`, task 25 `live-run-body`, `live-run-background`, `live-run-denied` and
`live-run-asked`, task 26 `live-format`, task 27 `live-skill` and `live-skill-doctor`, and task 29
`live-commit-asked` and `live-commit-policy`, task 39 `live-invisible`, task 32 `live-restore` and `live-stage`,
task 49 `live-space-dropped`, task 52 `live-format-dry`, task 54 `live-pipe-once`, task 46
`live-touched-index`, task 48 `live-script-write`, task 58 `edit-delete-join` and `live-lines-joined`, and
task 56 `live-read-width`, task 55 `live-verify-output`, and task 57 `live-subfolder-config`, all of which
passed on both. Since 2026-09-28 every probe turns off the lead's installed io-guard, which a user
setting enables in every session and the CLI loads from this checkout.

The design review named 2.1.281 as the first release whose `mcp_tool` hooks wait for their server. Today's hooks
reference names no version for that, so the floor rests on the probes instead. Older releases aren't tested.

## The features

"Needs" is a version the Claude Code docs name, or 2.1.281, the oldest release probed. A probe name refers to
`tools/probes/run_probe.py`.

| Feature | Needs | Probe | Without it |
|---|---|---|---|
| An `mcp_tool` hook calls a tool on the plugin's own server, and the tool's answer is the hook's decision | 2.1.281 | `time-mcp`, `mcp-gate`, `mcp-subst` | Command hooks: 52 ms per call in exec form on a small script, and 275 ms through `pyrun` running io-guard's hook ([`launcher.md`](launcher.md)) |
| An `mcp_tool` hook's server restarts on the next call, and a server that can't start fails open | 2.1.281 | `dead-server`, `dead-for-good`, `live-server-down` | The heartbeat hook warns once at the next turn (task 23) |
| A plugin's stdio server that fails to start is written to `~/.claude/mcp-needs-auth-cache.json`, and every session skips it for 15 minutes | 2.1.281 | `live-server-down` | io-guard's UserPromptSubmit hook reads that file and names the skip. If the file moves, the skip goes unnamed |
| An MCP server's environment carries `CLAUDE_CODE_SESSION_ID`, its own session's id | 2.1.281 | `era-legacy`, `live-server` | The server writes no heartbeat, and a server that died goes unnamed |
| A session's subagents call the plugin's one stdio server, each call as it comes, so their calls on one file overlap | 2.1.281 | `live-edit-parallel` | Nothing breaks: the lock table and `file_lock` serialise the calls whatever process or thread makes them (task 24) |
| A PreToolUse hook fires on the plugin's own MCP tool, and its `ask` brings up the permission prompt for a tool `--allowedTools` allowed | 2.1.281 | `live-run-asked`, `live-run-denied`, `live-restore` | `io.run` still refuses a command a deny rule meets, and refuses one an ask rule meets with `RULE_ASKED`, since no prompt put it to the user (task 25). `io.restore` writes nothing and answers `RESTORE_ASKED` (task 32) |
| A `UserPromptSubmit` command hook's `additionalContext` and `systemMessage` arrive at the start of the turn | 2.1.281 | `live-server-down` | A stopped server goes unnamed |
| A settings `ask` rule for `Bash(git commit *)` brings up the permission prompt in auto mode, and a `deny` rule refuses with none | 2.1.281 | `live-commit-asked` | The README's git snippet asks nothing in auto mode, and `commit.policy` still refuses a message the policy forbids (task 29) |
| PreToolUse `updatedInput` with `allow` runs the new input, byte-exact for Write | 2.1.281 | `rewrite-allow`, `write-bytes`, `edit-extend` | Refuse, with the fixed call in the reason |
| `updatedInput` with `ask` puts the new input in the permission prompt | 2.1.281 | `ask-prompt`, the desktop check | Refuse instead of asking |
| `updatedInput` with no `permissionDecision` applies, and the harness asks or approves as it would have (D26) | 2.1.281 | `write-quiet` | Answer `ask` with the conformed Write or Edit input, so no prompt is skipped |
| A hook's `allow` skips the auto-mode classifier | 2.1.281 | `auto-control`, `auto-allow` | Nothing changes. `refuse` is already the auto-mode default (D12) |
| PostToolUse `additionalContext` reaches the model | 2.1.281 | `read-context`, `live-read-profile` | The file's profile only in `io.read` (task 16) |
| `${transcript_path}` substitutes in an `mcp_tool` map, and the transcript records a refused Edit or Write with its `<tool_use_error>` | 2.1.281 | `live-diagnose`, `guard-fields` | A refused Edit or Write gets no diagnosis. A failed Read, Grep or Glob still does (task 20) |
| A failed Edit or Write names EPERM, EBUSY or EACCES in PostToolUseFailure's `error` when another process holds the file | 2.1.281 | `live-locked` | No holder is named, and the model sees the tool's own error alone (task 19) |
| An Edit straight after io-guard put back a file's endings and BOM goes through with no new Read | 2.1.281 | `live-verify-direct` | The repair's line already asks the agent to read the file again first (task 18) |
| PreToolUse `additionalContext` reaches the model, with or without a permission decision | 2.1.281 | `live-answers` | Say it after the call, in PostToolUse |
| `${tool_response}` and `${error}` substitute into an `mcp_tool` hook's map as JSON text and plain text | 2.1.281 | `guard-fields` | PostToolUse checks see no output (tasks 18, 21, 22) |
| A 145,599-byte Write arrives whole in `${tool_input}` | 2.1.283 | `guard-large` | A large Write goes unchecked |
| PostToolUseFailure fires for a failed Read, Grep, Glob or Bash call, with `error` and `additionalContext` | 2.1.281 | `failures`, `other-refusals`, `live-diagnose` | No diagnosis after the call (task 20) |
| `bashEditDiff` in a Bash result, with `bashEditDiffEnabled: true` | 2.1.281 | `bash-diff-on`, `bash-diff-off` | git status and modification times only (task 21) |
| `updatedToolOutput` in the tool's own output shape, Bash's and PowerShell's, and `classifierContext`. Without `persistedOutputPath` and `persistedOutputSize`, the new output reaches the model whole | 2.1.281 | `updated-output`, `command-output`, `live-results` | Claude Code's own 2 KB preview of a saved output, and the model reads the file again (task 22) |
| A failed Bash or PowerShell call's `error` holds `Exit code N`, then the call's stdout and stderr | 2.1.281 | `command-output` | The exit code alone, so no error line is found and no exit code is labelled (task 22) |
| An output over 30,000 characters reaches PostToolUse cut to 30,000, with `persistedOutputPath` naming the whole, already saved | 2.1.281 | `command-output`, `live-results` | io-guard reads the first 30,000 characters only (task 22) |
| `CLAUDE_ENV_FILE` for a SessionStart hook, reaching Bash calls and not PowerShell ones | 2.1.281 | `env-file`, `live-probe` | Bash runs without io-guard's UTF-8 settings (task 10) |
| A hook's environment names the Claude Code version in `AI_AGENT` | 2.1.281 | `live-probe` | `probe.json` has no version, and the Windows transport rules stay on |
| On Windows the Bash tool cuts a command near 7.8 KB and halves a run of backslashes that no double quote follows (#92543) | every release probed | this session's Bash tool, `live-move-ask` | Setting `FIXED_IN` in `checks/session_probe.py` to the fixing release turns both rules off for it (task 11) |
| On Windows the Bash tool runs Git Bash 5.2.37, which turns a slash argument for a Windows program into a path, and skips the prefixes `MSYS2_ARG_CONV_EXCL` names | 2.1.281 | this session's Bash tool, task 14 | `win.paths` exports a variable Git Bash ignores, and the arguments convert as before |
| Exec-form command hooks, which start a program with no shell | 2.1.281 | `time-exec`, `time-shell` | Shell form through Git Bash, about 33 ms slower |
| The legacy MCP era by default, and the 2026-07-28 era with `MCP_PROTOCOL_NEGOTIATION=auto` | 2.1.281 | `era-legacy`, `era-auto` | The server answers both eras (D9) |
| A modern `input_required` result resumes the call | 2.1.281 | `features-modern` | Ask through a hook instead |
| Legacy `elicitation/create` | 2.1.281, though no surface probed shows the form | `mcp-features`, the desktop check | A hook `ask` on the io tool's own call (task 25) |
| URL-mode elicitation | 2.1.281 per the design review, 2026-07-28 connections only | not probed | io-guard doesn't use it |
| Progress notifications | Accepted on 2.1.281. The desktop shows none | `mcp-features`, the desktop check | The result says how the run went |
| An MCP call still running after 2 minutes moves to the background | 2.1.212, docs | not probed | `io.run` hands back a handle first (task 25) |
| MCP Apps, a tool's `ui://` page | No release renders one | `mcp-features`, the desktop check | The same view as text and as a local page (task 33) |
| The MCP Tasks extension | No Claude client declares it | `era-legacy`, `era-auto` | Handles for background runs (task 25) |
| MCP tools prompt in default mode, whatever their annotations | 2.1.281 | `mcp-prompts`, `mcp-permit` | The README's settings snippet allows the read-only io tools |
| A plugin enabled on claude.ai loads in Claude Code | 2.1.273, docs | the desktop loaded `@synced` plugins | Install from the marketplace |
| On Windows an MCP server's `command` naming a file with no extension starts the `.cmd` file beside it through `cmd.exe`, each argument whole | 2.1.281 | `live-server`, which starts io-guard through `pyrun` | None on Windows: the server doesn't start, and `/mcp` shows why |
| The `env` block of `~/.claude/settings.json` reaches a plugin's MCP server and its command hooks | 2.1.281 | by hand on 2026-09-28, with `IOGUARD_PYTHON` set there only | `IOGUARD_PYTHON` as a user environment variable |
| The desktop app passes a plugin from a local-folder marketplace, or one synced from claude.ai, to each session as `<name>@inline`, whose saved options and data folder are that id's | desktop app 2.9939.2, with 2.1.281 | its log and its code, 2026-09-28 | Nothing to fall back on. io-guard reads no plugin option (D29) |
