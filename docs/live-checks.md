# Live checks

Some of what io-guard relies on only shows in a real Claude Code session: what a hook receives, what the harness
does with its answer, and what the model ends up seeing. This page lists each of those facts, with where and when
it was last confirmed and the probe that confirms it. [`compat.md`](compat.md) says what io-guard does when one
of them stops holding.

## Keep it current

A task that runs a live check updates its rows here, and in `compat.md`, in the same change. A row with no date
in the last few releases is a fact nobody has looked at lately. Rerun its probe before building on it.

The macOS column waits for the author's Mac, which is down. Task 36 holds every macOS check until it's back.

## The file and shell tools

Confirmed on Windows 10, in the desktop app's Code tab on its bundled 2.1.281, with Git Bash, PowerShell 7 and a
cp1252 console. The probes are in `.claude/tasks/baseline/eol_probe.py`, which stays local until task 34
publishes it.

| Fact | Windows | macOS | Confirmed |
|---|---|---|---|
| The Bash tool halves a `\\` that no double quote follows, even inside a quoted heredoc | 2.1.281 | waits for the Mac | 2026-09-27 |
| A Bash command over about 7.8 KB fails with "unexpected EOF" | 2.1.281 | waits for the Mac | 2026-09-27 |
| The PowerShell tool and the Write tool keep backslashes, and PowerShell takes a 9 KB here-string | 2.1.281 | waits for the Mac | 2026-09-27 |
| Edit keeps CRLF and a BOM, and strips trailing whitespace from `new_string` | 2.1.281 | waits for the Mac | 2026-09-27 |
| Write writes LF over a CRLF file and drops its BOM | 2.1.281 | waits for the Mac | 2026-09-27 |
| Read shows CRLF, LF and a BOM the same way | 2.1.281 | waits for the Mac | 2026-09-27 |
| Python prints through the cp1252 console code page | 2.1.281 | not a macOS issue | 2026-09-27 |

The PowerShell calls `shell.lint` refuses, confirmed through the PowerShell tool on PowerShell 7.6.6 during task
13. Each is an error in PowerShell itself, so any host shows it.

| Fact | Windows | macOS | Confirmed |
|---|---|---|---|
| Assigning `$PID`, `$HOME`, `$Host`, `$PSHOME`, `$ShellId`, `$true`, `$false`, `$ExecutionContext`, `$PSVersionTable`, `$Error`, `$PSCulture` or `$PSEdition` fails: "Cannot overwrite variable PID because it is read-only or constant." `$null`, `$input`, `$args` and `$Matches` take an assignment | 7.6.6 | waits for the Mac | 2026-09-27 |
| `foreach ($pid in ...)` fails the same way | 7.6.6 | waits for the Mac | 2026-09-27 |
| `Select-String -Recurse` fails: "A parameter cannot be found that matches parameter name 'Recurse'." | 7.6.6 | waits for the Mac | 2026-09-27 |
| `export X=1` is not a command, and `> /dev/null` fails: "Could not find a part of the path 'C:\dev\null'." | 7.6.6 | Unix PowerShell has a /dev/null | 2026-09-27 |
| A `pwsh` start that parses one command takes 191 to 218 ms, over five runs | 7.6.6 | waits for the Mac | 2026-09-27 |

## Plugins

Confirmed with the `claude` CLI at 2.1.283 and the desktop app on 2.1.281, during tasks 02 and 03.

| Fact | Probe | Windows | macOS | Confirmed |
|---|---|---|---|---|
| A manifest with no `version` validates, with one warning, and fails `--strict` | `claude plugin validate` | 2.1.283 | waits for the Mac | 2026-09-27 |
| A local marketplace installs, and the install tracks the HEAD commit | `claude plugin install` | 2.1.283 | waits for the Mac | 2026-09-27 |
| The desktop Code tab loads a plugin from a local marketplace | the lead, in the Code tab | 2.1.281 | waits for the Mac | 2026-09-27 |
| After an app restart, the desktop runs a cached copy of that plugin, not the marketplace folder | the io-probe server log | 2.1.281 | waits for the Mac | 2026-09-27 |
| The desktop Code tab loads plugins synced from claude.ai, hooks and MCP servers included | this repository's sessions | 2.1.281 | waits for the Mac | 2026-09-27 |
| io-guard's `.mcp.json` and `hooks.json` start its server and hooks, from the `python` setting | a headless session with io-guard installed | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| An unset `userConfig` option falls back to its default | io-guard installed with no `--config` | 2.1.283 | waits for the Mac | 2026-09-27 |
| A wrong `python` setting gives one warning, and every tool call still runs | io-guard installed with a wrong setting | 2.1.283 | waits for the Mac | 2026-09-27 |
| An `mcp_tool` hook answers in about 1.2 ms, against 53 ms in exec form and 130 ms through `hook.sh`, over 100 calls | `launch-mcp`, `launch-exec`, `launch-hooksh` | 2.1.283 | waits for the Mac | 2026-09-27 |

## Hooks and MCP

Confirmed with `tools/probes/run_probe.py`, whose `verdicts` command rechecks every row below. The numbers match
`.claude/tasks/context.md`, "Hooks and MCP", which holds the full results.

| Fact | Probe | Windows | macOS | Confirmed |
|---|---|---|---|---|
| 1. `updatedInput` with `allow` runs the new Bash command | `rewrite-allow` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 2. A Write `content` rewritten by a hook lands byte-exact, BOM and CRLF included | `write-bytes` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 3. An Edit with both strings extended by one character runs | `edit-extend` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 4. PostToolUse `additionalContext` on Read reaches the model | `read-context` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 5. PostToolUseFailure fires for a failed Read or Bash call, and not for an Edit whose anchor is missing | `failures` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 6. `bashEditDiff` arrives only with `bashEditDiffEnabled: true` | `bash-diff-on`, `bash-diff-off` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 7. `CLAUDE_ENV_FILE` variables reach later Bash calls | `env-file` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 8. `updatedToolOutput` works in the tool's own output shape, and `classifierContext` is accepted | `updated-output` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 9. An exec-form hook takes about 57 ms, and shell form about 90 ms | `time-exec`, `time-shell` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 10. A hook that crashes, times out or prints bad JSON leaves the tool call running | `hook-crash`, `hook-timeout`, `hook-badjson` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 11. The desktop Code tab loads a plugin from a local marketplace | the lead, in the Code tab | 2.1.281 | waits for the Mac | 2026-09-27 |
| 12. An `mcp_tool` hook reaches the plugin's own server in about 1.5 ms, and its answer is the decision | `time-mcp`, `mcp-gate`, `mcp-subst` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 13. `ask` with `updatedInput` shows the new command in the prompt | `ask-prompt`, the lead in the Code tab | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 14. A hook `allow` skips the auto-mode classifier | `auto-control`, `auto-allow` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 15. MCP servers connect in the legacy era unless `MCP_PROTOCOL_NEGOTIATION=auto` | `era-legacy`, `era-auto`, the Code tab | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 16. No surface probed shows an elicitation form or renders an MCP App. `input_required` resumes | `mcp-features`, `features-modern`, the lead in the Code tab | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 17. MCP tools prompt in default mode, whatever their annotations | `mcp-prompts`, `mcp-permit` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 18. A dead server restarts on the next hook call, and one that can't start fails open | `dead-server`, `dead-for-good` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 19. `${tool_response}` and `${error}` substitute like `${tool_input}` | `guard-fields` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 20. A Write of 145,599 bytes reaches an `mcp_tool` hook whole | `guard-large` | 2.1.283 | waits for the Mac | 2026-09-27 |
| 21. A `--plugin-dir` plugin takes its `userConfig` from `--settings`, under `pluginConfigs["<name>@inline"]` | by hand, task 08 | 2.1.283 | waits for the Mac | 2026-09-27 |
| 22. PreToolUse `additionalContext` reaches the model, with or without a permission decision | `live-answers` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 23. `CLAUDE_ENV_FILE` reaches Bash calls and not PowerShell calls | `live-probe` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 24. A hook's environment names the Claude Code version in `AI_AGENT` | `live-probe` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 25. The Bash tool halves a run of backslashes unless a double quote follows it | this session's Bash tool | 2.1.281 | waits for the Mac | 2026-09-27 |

## io-guard itself

Confirmed with the `live-*` probes, which run io-guard from this checkout with test checks added. The numbers
match `.claude/tasks/context.md`, "The hook entry point".

| Fact | Probe | Windows | macOS | Confirmed |
|---|---|---|---|---|
| With no check, the hooks answer every Bash, PowerShell, Write, Read and Edit call, and a failed Read | `live-empty` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| A check that raises on every event leaves every call running, and the other checks still answer | `live-broken` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| A rewrite in `allow` mode runs the new command, and a refusal's fix reaches the model | `live-answers` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| A rewrite in `refuse` mode gives the model the command to run instead, and it runs it | `live-refuse` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| The session probe writes `probe.json` in 54 to 143 ms, and its env file lets Bash's Python print U+2192 | `live-probe` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| A 9 KB heredoc is asked about with its body moved, and runs with both backslashes kept | `live-move-ask` | 2.1.283 | waits for the Mac | 2026-09-27 |
| In auto mode the same call is refused with the moved command, and the rerun runs | `live-move-auto` | 2.1.283 | waits for the Mac | 2026-09-27 |

## Not checked yet

- What the desktop shows the user when the io server can't start.
- Whether the desktop prompts for an MCP tool in manual mode. The CLI does.
- Whether Cowork renders an MCP App or shows an elicitation form.
- Where a `${tool_input}` substitution stops. 145,599 bytes arrive whole, and nothing larger was tried.
