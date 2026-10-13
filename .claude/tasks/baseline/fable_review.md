# Fable's review of the IO guard proposal (2026-09-27), and what I checked

Model output from a sub-agent, kept for reference. Checked claims are marked below the report.

## Checked against the docs and GitHub on 2026-09-27

| Fable's claim | Result | Source |
|---|---|---|
| Checkpoints track only Claude's file editing tools. Bash changes are not tracked | Confirmed: "Checkpointing does not track files modified by Bash commands ... Only direct file edits made through Claude's file editing tools are tracked." | code.claude.com/docs/en/checkpointing |
| A bare Bash deny removes the tool from Claude's context | Confirmed: "As a deny rule, both forms remove the tool from Claude's context." | docs/en/permissions |
| Settings skip any mcp__ rule with parentheses | Confirmed: "it skips any `mcp__` rule that has parentheses" | docs/en/permissions |
| PreToolUse updatedInput replaces the input, rules re-evaluated | Confirmed, but "Works with `permissionDecision: "allow"` only". Fable said allow or ask | docs/en/hooks |
| Exec-form hooks run without a shell. Shell form: sh -c on macOS and Linux, Git Bash on Windows | Confirmed | docs/en/hooks |
| FileChanged and PostToolUseFailure events exist | Confirmed | docs/en/hooks |
| A plugin's settings.json applies only `agent` and `subagentStatusLine` | Confirmed: "every other key is dropped" | docs/en/plugins/components |
| MCP output: 25,000 tokens by default, warning at 10,000, overflow saved to a file | Confirmed | docs/en/mcp |
| MCP tools are deferred behind tool search by default | Confirmed | docs/en/mcp |
| MCP calls go to the background after 2 minutes (v2.1.212+) | Confirmed | docs/en/mcp |
| Sandbox: macOS, Linux and WSL2 only. It wraps Bash, PowerShell and Monitor | Confirmed: "Native Windows is not supported." | docs/en/sandboxing |
| Issue #92543: -c cut at 8,181 to 8,190 chars, every `\\` halved, libuv MS-CRT quoting against MSYS2 | Confirmed, open, filed 2026-09-06. Its suggested fix: hand the script to bash through stdin or a temp file | github.com/anthropics/claude-code/issues/92543 |
| Issue #95653: plugin bin/ PATH entries inlined into the same bash -c string | Confirmed, closed 2026-09-20 | github.com/anthropics/claude-code/issues/95653 |
| bashEditDiff, CLAUDE_ENV_FILE, updatedToolOutput, classifierContext | Not found in my fetch of the hooks page. Unverified until tested | - |
| uv downloads Python by itself | Not re-verified | - |

## The report (verbatim)

### 1. Pushback first

**Right in the proposal.** Prose rules do not hold: 417 scratchpad writers and 1,819 workaround scripts exist despite the guard hook and CLAUDE.md, and the harness itself pushes the other way (this session's auto-mode text tells the model to prefer `sed, heredocs, or short scripts`; hooks.md confirms Claude Code "directs Claude to edit files through Bash" in auto mode). A mechanism that fixes or refuses at the boundary, with a structured error and a fix hint, is the correct shape. Packaging must be portable: a plugin is that package.

**Wrong: deny Bash/PowerShell/Edit/Write and route everything through one MCP tool.** What breaks, per the docs:

- Checkpoints/rewind track only "Claude's file editing tools"; Bash-made changes are not tracked. An MCP writer is in the same class as Bash: every write becomes un-rewindable. The desktop diff pane's detection mechanism is undocumented; treat MCP writes as likely invisible there too.
- The built-in read-before-edit and modified-since-read guards fire on the next built-in Edit after any external write, so an MCP editor causes the STL-1 class instead of curing it.
- Permission rules cannot match an MCP tool's parameters in settings ("skips any `mcp__` rule that has parentheses", only `--disallowedTools` per session). Every call to one `run` tool is one whole-tool decision; `permissions.ask: ["Bash(git push *)"]`-style human checkpoints disappear, and so do the classifier's shell-specific checks.
- `run_in_background`, `/tasks`, `bashEditDiff`, and the Monitor tool are Bash-tool features. MCP calls do auto-background after 2 min with a task notification, which covers long builds but not "start a server and keep going".
- MCP tools are deferred behind ToolSearch by default; the model must search before each first use. `ENABLE_TOOL_SEARCH=false|auto:N` trades context for that.
- A bare `Bash` deny "removes the tool from Claude's context", so routing-around is guaranteed: PowerShell first (deny that too), then `python`/`node` inside our tool. The block only moves the problem into a tool we control, which is the one good argument, and it is satisfied by controlling the transport, not by denying Bash.
- Sandboxing is macOS/Linux/WSL2 only, "Native Windows is not supported"; on the Mac it wraps Bash/PowerShell/Monitor, not MCP.

**Also known upstream, unfixed:** issue #92543 reports exactly facts 1-2 (`bash.exe -c` cut at 8,181-8,190 chars, every `\\` halved: libuv quotes by MS-CRT rules, MSYS2 bash re-reads them; open, no fix) and #95653 shows plugin `bin/` PATH entries inlined into that same `bash -c` string, so each enabled plugin shrinks the budget: never ship `bin/`, and measure the budget per machine.

**Conclusion:** keep the built-ins as the transport the harness understands; put the intelligence in hooks around them; add an MCP server only for what built-ins cannot express.

### 3. Generic principles: one mechanism per layer

1. Transport layer (command text to shell). Rule: content never travels in the command string. PreToolUse `Bash|PowerShell`: if the command carries a body (heredoc, `-c`, `echo >`), rewrite it via `updatedInput` into a scratch file plus `bash "<file>"`/`python "<file>"`; else if over the measured budget, refuse. Same hook: MSYS slash-tokens, reserved names, backticks in double quotes, `set -o pipefail` prepended when a pipe is present.
2. Bytes layer (content to disk). Rule: the file's existing bytes are the contract (EOL, BOM, encoding, final newline, indent char). PreToolUse `Write|Edit` conforms `content`/`new_string` via `updatedInput`; PostToolUse verifies and repairs (trailing whitespace the harness strips, BOM, EOL counts, no new U+FFFD/NUL/C0, size not collapsed, PUA count) and reports.
3. Stale-view layer. Rule: every miss returns the fix. PostToolUseFailure `Edit` diagnoses the anchor (closest whitespace-normalised match, line numbers, visible CR/BOM/PUA, match count, shortest unique anchor) as `additionalContext`. PostToolUse `Bash` lists files changed on disk and says "re-Read before Edit".
4. Output layer. Rule: exit status and errors are structured, logs go to files. SessionStart sets `PYTHONUTF8=1 PYTHONIOENCODING=utf-8 GIT_PAGER=cat DOTNET_CLI_UI_LANGUAGE=en VSLANG=1033`; PostToolUse `Bash` annotates benign exit-1 and filtered builds; `io.run` returns `{exit, ok, log_path, errors[], tail}`.

Classes unseen yet fall into the same layers, e.g. macOS: `/bin/bash` 3.2 against Git Bash 5 (`readarray`, `${x,,}`), BSD `sed -i ''`/`stat -f`/no `grep -P`, APFS NFD filenames, case-insensitive paths on both. The transport guard gets a "portable subset" lint driven by the detected bash version, not new rules per bug.

### 4. Architecture

Plugin `io-guard` in the kit (`plugins/io-guard/`), registered as a local marketplace, installed user scope on each machine, also listed in each project's `.claude/settings.json` `enabledPlugins`.

- `hooks/hooks.json` (exec form, one Python codebase, stdlib only): PreToolUse `Bash|PowerShell`, PreToolUse `Write|Edit`, PostToolUse `Edit|Write`, PostToolUseFailure `Edit`, PostToolUse `Bash|PowerShell`, SessionStart (platform probe: OS, bash version, whether `\\` halves, measured `-c` budget, git snapshot).
- `.mcp.json`: stdio server `io` with `io.read` (byte-exact, contract report, ranges), `io.edit` (batch, all-or-nothing, anchor diagnostics, contract-preserving; result says "re-Read before built-in Edit"), `io.write` (write roots: worktree, scratchpad, memory), `io.run` (argv list, no shell; or `script` body written to a file; cwd pinned; logs to file; error-regex profiles per project). Elicitation only for user decisions (a locked file's holder: wait or stop).
- `skills/io-guard/SKILL.md`: the error codes and the fix vocabulary.
- Runtime: Python via uv (`command: "uv"`, `args: ["run","--project","${CLAUDE_PLUGIN_ROOT}", ...]`), installed by `brew install uv` or `winget install --id=astral-sh.uv -e`. Platform switches: `sys.platform`, `tool_name`, and the SessionStart probe file under `${CLAUDE_PLUGIN_DATA}`.
- Settings a plugin cannot carry, written by the installer to `~/.claude/settings.json`: `permissions.ask` for `git commit` and `git push` in Bash and PowerShell, `permissions.deny` for `git checkout -- *` and `git reset --hard *`, `env` for `ENABLE_TOOL_SEARCH=auto:5`. Do not deny Bash or PowerShell.

Structured error:
```json
{"ok":false,"code":"ANCHOR_AMBIGUOUS","platform":"win32","file":"C:/.../X.cpp",
 "message":"old_string matches at lines 41 and 208.",
 "evidence":{"eol":"crlf","bom":true,"matches":[{"line":41,"context":"..."}]},
 "fix":{"tool":"Edit","input":{"old_string":"<shortest unique anchor>","new_string":"..."}}}
```
Codes: TRANSPORT_BUDGET, BACKSLASH_TRANSPORT, MSYS_PATH, RESERVED_NAME, SHELL_WRITE, EOL_MISMATCH, BOM_CHANGED, ENCODING_INVALID, TRAILING_WS_STRIPPED, ANCHOR_NOT_FOUND, ANCHOR_AMBIGUOUS, STALE_VIEW, OUTSIDE_WRITE_ROOT, FILE_LOCKED, PIPE_HIDES_EXIT, FILTER_CUTS_OUTPUT.

Migration: (1) the user-scope settings; (2) move the two existing hooks into the plugin, port install.ps1 to Python (on macOS the links are symlinks, which checkpoint restore skips); (3) transport guard replaces shell-write-guard.py; (4) byte-contract and anchor-diagnosis hooks; (5) MCP server; (6) acceptance = rerun tx_scan.py on new transcripts and beat the counts (71 misses, 82/55 stale, 160 EOF, 417 writers).

Windows-only classes: SHW-2, SHW-4, PTH-4, PTH-5 (creation), SHL-2, LCK-1, BYT-5, BYT-8, SHL-4 to SHL-7, OUT-4. Everywhere: ANC-*, STL-*, BYT-1/2/6/7/9/11/12, SHW-1/5/6, OUT-1/2/3/5-8, RUN-*, PTH-1 to 3, GIT-*, INP-*, GRD-2/3.

### 5. Not asked for

- Repo `.gitattributes` with explicit `eol` per extension and `core.autocrlf=false` ends the 432 warnings; a pre-commit byte guard reuses the same contract module (hook, MCP, git hook: one module, three call sites).
- The auto-mode nudge is best defeated by making the heredoc route work (rewrite to file) rather than by refusing it.
- Trim CLAUDE.md.template: rules that a hook enforces leave the prose.

### 6. Top risks

1. Hook latency: a Python spawn on every Bash/Edit/Write (~100 ms warm). Warm at SessionStart, stdlib only.
2. `updatedInput` rewrites run something the model did not write, and the classifier judges the rewritten text. Keep rewrites mechanical and logged, refuse otherwise.
3. Post-hoc repairs (trailing whitespace, BOM) are writes outside checkpoint tracking. Keep them minimal and reported.
4. The Windows budget depends on the machine and the plugin count (#95653). Probe it, do not hard-code 7.8 KB. The halving may be fixed upstream (#92543), and the probe retires the rule.
5. MCP writes are invisible to checkpoints, the diff pane and read-tracking. Keep built-ins as default writers, `io.edit` for batches.
6. `bashEditDiff` is beta and misses ignored files. `FileChanged` needs literal names. A git fallback is needed.
7. Cross-platform installer and link type (junction against symlink), and macOS sandbox write rules around a linked kit.
8. Ask rules for commit and push block unattended `-p` runs by design.
