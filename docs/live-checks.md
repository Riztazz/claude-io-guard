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
| The Bash tool halves every `\\`, even inside a quoted heredoc | 2.1.281 | waits for the Mac | 2026-09-27 |
| A Bash command over about 7.8 KB fails with "unexpected EOF" | 2.1.281 | waits for the Mac | 2026-09-27 |
| The PowerShell tool and the Write tool keep backslashes, and PowerShell takes a 9 KB here-string | 2.1.281 | waits for the Mac | 2026-09-27 |
| Edit keeps CRLF and a BOM, and strips trailing whitespace from `new_string` | 2.1.281 | waits for the Mac | 2026-09-27 |
| Write writes LF over a CRLF file and drops its BOM | 2.1.281 | waits for the Mac | 2026-09-27 |
| Read shows CRLF, LF and a BOM the same way | 2.1.281 | waits for the Mac | 2026-09-27 |
| Python prints through the cp1252 console code page | 2.1.281 | not a macOS issue | 2026-09-27 |

## Plugins

Confirmed with the `claude` CLI at 2.1.283 and the desktop app on 2.1.281, during tasks 02 and 03.

| Fact | Probe | Windows | macOS | Confirmed |
|---|---|---|---|---|
| A manifest with no `version` validates, with one warning, and fails `--strict` | `claude plugin validate` | 2.1.283 | waits for the Mac | 2026-09-27 |
| A local marketplace installs, and the install tracks the HEAD commit | `claude plugin install` | 2.1.283 | waits for the Mac | 2026-09-27 |
| The desktop Code tab loads a plugin from a local marketplace | the lead, in the Code tab | 2.1.281 | waits for the Mac | 2026-09-27 |
| After an app restart, the desktop runs a cached copy of that plugin, not the marketplace folder | the io-probe server log | 2.1.281 | waits for the Mac | 2026-09-27 |
| The desktop Code tab loads plugins synced from claude.ai, hooks and MCP servers included | this repository's sessions | 2.1.281 | waits for the Mac | 2026-09-27 |

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

## Not checked yet

- What the desktop shows the user when the io server can't start.
- Whether the desktop prompts for an MCP tool in manual mode. The CLI does.
- Whether Cowork renders an MCP App or shows an elicitation form.
- How large a `${tool_input}` substitution can get, and `${tool_response}`. Task 08 checks both.
- Whether `${user_config.python}` falls back to its default when the user never set it. Task 06 checks it.
