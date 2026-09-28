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
| Edit keeps CRLF and a BOM | 2.1.281 | waits for the Mac | 2026-09-27 |
| Write writes LF over a CRLF file and drops its BOM | 2.1.281 | waits for the Mac | 2026-09-27 |
| Read shows CRLF, LF and a BOM the same way | 2.1.281 | waits for the Mac | 2026-09-27 |
| Python prints through the cp1252 console code page | 2.1.281 | not a macOS issue | 2026-09-27 |
| Git Bash 5.2.37 hands a Windows program `/Game/X` as `C:/Program Files/Git/Game/X`, `/PID` as `C:/Program Files/Git/PID`, `/F` as `F:/` and `/p:x` as `p:x`, and turns `/c/Users` and `/tmp` into Windows paths | 2.1.281 | not a macOS issue | 2026-09-27 |
| `MSYS2_ARG_CONV_EXCL` keeps the prefixes it names, case-sensitive, and `/c/...` still converts. `MSYS_NO_PATHCONV=1` stops every conversion, `/c/...` included | 2.1.281 | not a macOS issue | 2026-09-27 |
| `cmd /c` opens cmd without running the command, because `/c` arrives as `C:/`. `2>nul` writes a real file named `nul` | 2.1.281 | not a macOS issue | 2026-09-27 |

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
| io-guard's `.mcp.json` and `hooks.json` start its server and hooks through `pyrun`, with nothing set | `live-empty`, `live-server`, `live-server-down`, `live-answers` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| An MCP command naming a file with no extension starts the `.cmd` beside it, each argument whole | a one-off plugin, then `live-server` | 2.1.281, 2.1.283 | not needed: macOS runs `pyrun` | 2026-09-28 |
| `IOGUARD_PYTHON` in the `env` block of `settings.json` reaches the server, and a wrong value is named in its MCP log | by hand, `--settings` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| No server process outlives its session, through `cmd.exe` and `py` | eight `live-*` sessions, then the process list | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| After an app restart, the desktop passes a plugin from a local-folder marketplace to each session as `<name>@inline`, and the options saved for its marketplace id don't reach it | the desktop's `main.log`, and io-guard's data folders | 2.1.281 | waits for the Mac | 2026-09-28 |
| Passed as `io-guard@inline`, the desktop's io-guard starts its server through `pyrun` with nothing set, and its hooks, server and heartbeat all use `~/.claude/io-guard` | a Code tab session after the lead's restart | 2.1.281 | waits for the Mac | 2026-09-28 |
| An unset `userConfig` option falls back to its default | io-guard installed with no `--config` | 2.1.283 | waits for the Mac | 2026-09-27 |
| An `mcp_tool` hook answers in 37.9 ms at p50, against 52.1 ms in exec form on a small script and 275.0 ms through `pyrun` running io-guard's hook, over 100 calls. The first measured 1.2 ms on 2026-09-27, on the same release (task 43) | `launch-mcp`, `launch-exec`, `launch-pyrun` | 2.1.283 | waits for the Mac | 2026-09-28 |

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
| 27. `updatedInput` with no permission decision applies, and the harness asks or approves as it would have | `write-quiet` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 28. The Edit tool keeps a trailing space in `new_string`. A trailing space the model is asked for is gone from its own call before any hook sees it | `edit-trailing`, the first `live-conform` run, `live-space-dropped` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| 29. An Edit straight after io-guard put back a file's endings and BOM succeeds with no new Read | `live-verify-direct` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 30. An Edit or Write rejected as a `<tool_use_error>` fires no hook. A failed Read, Grep or Glob fires PostToolUseFailure | `edit-refusals`, `other-refusals` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 31. `${transcript_path}` substitutes in an `mcp_tool` map, and the transcript holds a refused call and its error | `live-diagnose`, `guard-fields` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| 32. A failed Bash call's `error` holds its exit code line, then its stdout and stderr. An output over 30,000 characters reaches PostToolUse cut to 30,000, with `persistedOutputPath` naming the saved whole, already on disk. An `updatedToolOutput` without the two `persistedOutput` fields reaches the model whole, for Bash and for PowerShell | `command-output` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| 33. A plugin's stdio server that fails to start is cached in `~/.claude/mcp-needs-auth-cache.json`, and every session in the next 15 minutes skips it, CLI and desktop alike | `live-server-down` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| 34. An MCP server's environment names its own session in `CLAUDE_CODE_SESSION_ID` | `era-legacy` | 2.1.283 | waits for the Mac | 2026-09-28 |
| 39. The desktop app rewrites a memory note's frontmatter after a Write or an Edit, before PostToolUse reads it. `claude -p` leaves the note as written | the lead's desktop sessions, a one-off `claude -p` run | desktop 2.1.281, CLI 2.1.283 | waits for the Mac | 2026-09-28 |

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
| After a Read, the file's profile line reaches the model, which quotes it | `live-read-profile` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| A Write of LF text over a BOM and CRLF file lands with the BOM and CRLF | `live-conform` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| A refused Edit's missing or repeated `old_string`, a missing file or folder, a Read too large and a pattern ripgrep rejects each get their diagnosis before the model's next step | `live-diagnose` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| An Edit whose `old_string` equals its `new_string` gets Claude Code's own "No changes to make" and nothing from io-guard | `live-diagnose` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| A shell command that changed a file the model had read names it with the step to read it again, and one that converted its endings names that too | `live-touched` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| An Edit of a read-only file that git marks lockable is refused with the `git lfs lock` step | `live-read-only` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| An Edit of a file another process holds, sharing reads only, fails with EPERM, and the model learns the holder's name and process id | `live-locked` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| A replace_all Edit whose lost trailing space would join `.Branch.ToInt(),1` is refused with `SPACE_DROPPED`, and the model's Edits one character longer leave `ToInt(), 1` and `ToInt(), 2` | `live-space-dropped` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| With `conform.write` off, a Write that drops a BOM and CRLF gets both put back after it, the model sees `EOL_CONVERTED`, and the next Edit lands in the file's own bytes | `live-verify`, `live-verify-direct` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |
| The io server connects, answers the hooks, and returns `io.read` of a CRLF file with a BOM in its structured result, and its heartbeat records the legacy era, or the modern one under `MCP_PROTOCOL_NEGOTIATION=auto` | `live-server`, `live-server-modern` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| A server that dies and cannot start again leaves the tool calls running, and the next turn names SERVER_DOWN | `live-server-down` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| Three subagents started in one message make 30 interleaved `io.edit` calls on one BOM and CRLF file, and every edit lands, in the file's BOM and CRLF | `live-edit-parallel` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| A 21 KB Python body with 500 pairs of backslashes reaches its file through `io.run` byte for byte, and Python prints both backslashes of each pair | `live-run-body` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| A 15-minute background `io.run` reports `running` through `io.status` while it runs, and `ended` with exit code 0 after it | `live-run-background` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| With `Bash(git push *)` denied, `io.run` of `git push origin main` is refused with `RULE_DENIED`. With `Bash(git fetch *)` in the ask rules, the permission prompt receives the `io.run` call, and the approved run goes through | `live-run-denied`, `live-run-asked` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| After `io.snapshot` and an `io.edit`, the hook on `io.restore` answers `RESTORE_ASKED`, the permission prompt receives the call, and the approved restore puts the file's CRLF bytes back | `live-restore` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| The journal records an `io.edit` under the tag `io.snapshot` named, and a built-in Write and Edit with their lines, from the io server | `live-restore`, `live-verify`, the journal they wrote | 2.1.283 | waits for the Mac | 2026-09-28 |
| After an `io.edit` of lines 3 and 20, `io.stage` of line 3 leaves the index holding line 3's change alone, line 20's in the working tree, and no commit | `live-stage` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| A Write that puts an invisible character inside a Python string gets `INVISIBLE_ADDED` naming the character and its line | `live-invisible` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| In auto mode, a project's `permissions.ask` rule for `Bash(git commit *)` sends the commit to the permission prompt, and its `permissions.deny` rule refuses `git reset --hard` with no prompt | `live-commit-asked` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| With `commit_policy.forbid` naming `Co-Authored-By`, a commit carrying that line is refused with `COMMIT_POLICY`, and the model commits again without it | `live-commit-policy` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| The session's telemetry holds one `tools/call` line for each io tool call, `io.edit` and `io.format` in `live-format`, with its time, extension and bytes written | `live-format` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| `/skill-doctor` lists the plugin's skill as `io-guard:io-guard`, and its one-line listing costs under 20 tokens a turn | `live-skill-doctor` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| In dontAsk mode, commands refused with `SHELL_WRITE`, `MSYS_PATH`, `TRAILING_BACKSLASH_QUOTE`, `POWERSHELL_TRAP` and `DIALECT_MISMATCH` each get one retry, and it runs. Haiku recovered from the refusal's own text and loaded no skill | `live-skill` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| After an `io.edit` adds a badly formatted line to a committed BOM and CRLF `.cpp`, `io.format` runs clang-format from `PATH` over that line only: it becomes five formatted lines, the badly formatted committed line stays, and every line keeps CRLF although the `.clang-format` names `LineEnding: LF` | `live-format` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-28 |
| A saved Bash or PowerShell output comes back as its first and last 20 lines with the file's path, and the model reads no file. grep's exit code 1 that stopped an `&&` chain is labelled as its answer, and a traceback behind `\| tail` is named with tail's exit code | `live-results` | 2.1.281, 2.1.283 | waits for the Mac | 2026-09-27 |

## Not checked yet

- What the desktop shows the user when the io server can't start.
- Whether the desktop prompts for an MCP tool in manual mode. The CLI does.
- Whether Cowork renders an MCP App or shows an elicitation form.
- Where a `${tool_input}` substitution stops. 145,599 bytes arrive whole, and nothing larger was tried.
