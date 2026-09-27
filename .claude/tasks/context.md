# Context

Everything the tasks rest on, gathered on 2026-09-27 from four Unreal Engine projects (CLICKER, OrbitalDrift,
SmartTablesHost, UNREAL-SHARED), a friend's scan of five other projects, a design review, and the Claude Code docs.
The full catalog with evidence is `baseline/io_traps.html`, published privately at
https://claude.ai/artifact/NDhF5JoHcXy6mDDPSecZLu. The first design review and the checks on it are
`baseline/fable_review.md`. The design a task builds from is `docs/design/architecture.md`, and Fable's second review,
which it answers, is `docs/design/review.md`. Both reviews use the task numbers from before the renumbering of
2026-09-27, and `.claude/tasks/README.md` maps them.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | A Claude Code plugin in the GitHub repo `Riztazz/claude-io-guard`, installed from claude.ai (Customize > Plugins) or with `/plugin marketplace add Riztazz/claude-io-guard` | One install per account or machine, the same code on Windows and macOS, updates from git |
| D2 | Hooks around the built-in tools do the checking and fixing. Bash and PowerShell stay enabled | A deny rule on Bash removes it from Claude's context and the model routes around it. Rewind covers only the built-in file tools. Settings cannot match an MCP tool's arguments |
| D3 | A small MCP server adds only what the built-ins cannot do: batch edit, splice, append, run with an argument list, format hunks, snapshots, hunk staging | Every MCP write is invisible to rewind and to read tracking, so it stays the exception |
| D4 | One codebase, Python standard library only, the platform detected at run time | Claude Code installs no Python packages for a plugin. The lead works on Windows and macOS |
| D5 | The guard adds no escaping layer. Content travels as a tool argument or in a file, never inside a shell string the guard builds | The failures come from the shell-string layer. Another layer would add its own |
| D6 | Fix only when the fix is mechanical and cannot change meaning, and say what was fixed. Otherwise refuse with a structured error that carries a corrected call | A silent fix teaches the model nothing. A vague refusal costs a retry |
| D7 | Fail open: an internal guard error allows the call, logs itself and warns once. Confirmed by the lead on 2026-09-27 | A guard bug must never block a session |
| D8 | Transcripts, the replay corpus and telemetry stay on the machine. Nothing from them is committed | They hold the lead's paths and project content |
| D9 | The io MCP server is dual-era: it answers the modern 2026-07-28 protocol (`server/discover`, per-request `_meta`) and the legacy `initialize` handshake | Claude Code's v2 runtime connects to stdio servers the legacy way unless `MCP_PROTOCOL_NEGOTIATION=auto` is set |
| D10 | MCP Apps are an optional layer. Every tool that has a UI also returns text and `structuredContent` | Only claude.ai and Claude Desktop render Apps, Chat ignores local servers, and Claude Code support is undocumented |
| D11 | The Unreal kit (UNREAL-SHARED) owns every rule and skill. This repository links the kit's generic group through the kit's `generic` profile, and the links stay gitignored. A release copies a snapshot of them into the repository (task 34) | One source for every project. Git writes through a tracked junction into the kit (verified live below), so the links are never tracked |
| D12 | A rewrite of a command is a user setting per permission mode, `transport.rewrite_mode`: `refuse` (the call is refused and the reason carries the corrected command), `ask` or `allow`. Defaults: `refuse` in auto and dontAsk, `ask` in default, acceptEdits and plan, `allow` in bypassPermissions. A project file may not set `allow` | A hook `allow` skips the permission prompt and the auto-mode classifier, so a silent rewrite would approve a command nobody judged. The lead set the auto-mode order: refuse first, ask second, allow third |
| D13 | One io server per Claude Code session, shared by the session's subagents, runs the hook checks and the io tools. It is thread-safe: a reader thread, four workers, one writer lock and a lock per file. Two sessions on one project are two servers, kept safe on disk by an atomic replace plus one lock file per edited file, one telemetry file per session, and a config that is read-only after load. A process per call remains only as the fallback | A Python start per call costs about 100 ms. A daemon per project needs its own lifecycle and IPC, and one crash would stop guarding in every session of the project |
| D14 | `io.run` obeys the user's Bash and PowerShell deny and ask rules: deny refuses, ask elicits the user's yes | Settings cannot match an MCP tool's arguments, so without parity `io.run` is a way around a rule such as `Bash(git push *)` |
| D15 | Python 3.14 is the floor. Hooks and the server start `${user_config.python}`, which defaults to `python3`. On Windows with python.org Python the user sets `python` once, because `python3` there is the Microsoft Store stub | The lead runs 3.14 on Windows and will on the Mac. `python3` is right on macOS and Linux |
| D16 | Every policy value is a config key with its default in code. The time budget defaults to 300 ms, past which checks that run a subprocess are skipped, and a 2,000 ms cap, past which every remaining check is skipped | The lead: "configurable as everything else should be" |
| D17 | Python lines stop at 110 characters, code and comments alike | The width the rules and skills already wrap at |
| D18 | Until 1.0, `plugin.json` has no `version` and installs track commits. From 1.0 on, semantic version tags with release notes | Fast iteration now, a known-good version for users later |
| D19 | Everything is published except the rows from the friend's scan: the publish scrub (task 34) removes them, the EXT test-helper rows included | The friend's findings are third-party content |
| D20 | The task files are numbered in build order, and every dependency points to a lower number. Hunk staging and the dashboard come after the measured result | The lead asked for one linear order |
| D21 | The lead's Mac is down from 2026-09-27 for the foreseeable future. Live checks run on Windows only, CI still runs macOS on GitHub's runners, and the live macOS checks wait in task 36. Code assumes the Mac has Python 3.14 | Nothing can be checked live on a Mac until it is back |
| D22 | Telemetry copied into a clone goes in `events/`, and a report page written into a clone goes in `reports/`. Both are gitignored at the root, beside `corpus/`. Chosen by the lead on 2026-09-27 | No task named an export path, and D8 keeps telemetry out of git. A bare `*.jsonl` would also hide the conformance scripts in `tests/mcp/requests/` |
| D23 | GitHub Pages serves `docs/` from `main`, and the README links the drawing there: `https://riztazz.github.io/claude-io-guard/architecture.svg`. `docs/.nojekyll` makes Pages serve the folder as files. Chosen by the lead on 2026-09-27 | GitHub shows an SVG in a README, and in the file view, as an image with no script. `raw.githubusercontent.com` and `gist.githubusercontent.com` both send `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`, which blocks it too. Pages sends no such header, checked with curl on 2026-09-27 |

## Surfaces

The lead works mostly in the Claude Code desktop app (the Code tab), on Windows and on a Mac. Every live check runs
there first, then in the CLI. On 2026-09-27 the Windows machine has the desktop app with bundled Claude Code
2.1.281 and the `claude` CLI at 2.1.283. Both meet the 2.1.273 floor for plugins synced from claude.ai. The Mac is
down (D21). The Windows machine has `python` 3.14.0 and `py`, and its `python3` is the Microsoft Store stub, which
prints "Python was not found".

`workbench/` at the repository root holds 13 files the lead had copied from SmartTablesHost on 2026-09-27, byte
for byte, to test on. They are the six largest test files and their shared header, the 133 KB `SmartTable.h`, and
four files with bytes of their own: LF with tab indent, one lone CR in a CRLF file, a 58 KB INI of six lines, and
CRLF Python with mixed indent. All are UTF-8 and ASCII, and none has a BOM. SmartTablesHost holds no BOM, no mixed
endings and no invalid UTF-8, so those cases come from task 05's fixtures.

## Verified live on 2026-09-27

Windows 10, Claude Code desktop (bundled 2.1.281), Git Bash, PowerShell 7, Python 3.14 with a cp1252 console. The
`claude` CLI was 2.1.246 during these tests and has since been updated to 2.1.283.

| Claim | Test | Result |
|---|---|---|
| The Bash tool halves backslashes | `echo 'a\\b' \| od -c` | `a \ b`. `'a\\\\b'` gives two backslashes |
| A quoted heredoc does not protect them | `python - <<'PY'` then `len(r"\\n")` | 2, where 3 was sent |
| The PowerShell tool keeps them | `'a\\b'.Length` | 4 |
| The PowerShell tool takes a large here-string | 9 KB here-string, `.Length` | 8,971, both backslashes kept |
| The Write tool keeps them | A 125 KB file holding `\\` and `\\\\` | Byte-exact |
| Bash commands over about 7.8 KB fail | `cat <<'EOF' \| wc -c` with 5.3, 7.8 and 9.0 KB bodies | 5,322, then twice `/usr/bin/bash: -c: line 1: unexpected EOF while looking for matching `''` |
| An apostrophe is not the trigger | The 9.0 KB body with no apostrophe | Same error |
| Line count is not the trigger | 20 and 70-line heredocs with an apostrophe | 20 and 70 |
| Edit keeps CRLF | A newline inside new_string, in a CRLF file | `TWO\r\nadded\r\n` |
| Edit keeps a BOM | An edit in a CRLF file with a BOM | BOM and CRLF kept |
| Edit strips trailing whitespace from new_string | new_string `one = ` | `one =` |
| Write writes LF over a CRLF file | Write `alpha`, `beta` | `alpha\nbeta\n` |
| Write drops a BOM | The same Write over a BOM file | No BOM |
| Read hides endings and BOM | Read of CRLF, LF and CRLF-with-BOM probes | Three identical outputs |
| Python prints through cp1252 | `print()` of U+2192 | `UnicodeEncodeError: 'charmap' codec can't encode character '\u2192' in position 22: character maps to <undefined>` |

The probes are `baseline/eol_probe.py`.

Rules through a junction, checked on 2026-09-27 with Claude Code 2.1.281 and 2.1.283:

- **Claude Code loads a rule, or an `@` import, only when its real path is inside the project.** A junction's real
  path is the kit, so the seven rules behind `.claude/rules/shared` did not load, and neither did an import through a
  junction or an import by absolute path from outside.
- **The one switch is `hasClaudeMdExternalIncludesApproved`**, under the project's key in `~/.claude.json`. The desktop
  app and `claude -p` never ask for it. The kit's installer sets it for every project it links rules into.
- **With the flag set, a new `claude -p` session here lists all seven shared rules**, beside `this-repo.md`,
  `docs.md` and `CLAUDE.md`.
- **Skills load through a junction with no approval.**
- **A nested `@` import resolves against the importing file's folder**, not the project root.

Git through a junction, tested on scratch copies on 2026-09-27 with Git for Windows:

| Claim | Test | Result |
|---|---|---|
| Git walks into a junction | `git add -A` in a repo holding a junction to a folder with one file | The file is added as `100644` content |
| An edit in the linked folder shows as a change | Append a line to the file in the linked folder | `M` in the repo |
| Discarding a change writes through | `git checkout -- .` in the repo | The linked folder's own edit is reverted |
| Removing a tracked file deletes through | `git rm -r` on a branch, then switch back | The linked folder's file is gone, and switching back does not restore it |

Git attributes, checked on 2026-09-27 with Git for Windows 2.49.0 and `core.autocrlf=true`, after task 01 wrote
`.gitattributes`:

| Claim | Test | Result |
|---|---|---|
| A path under `tests/fixtures/` is not text | `git check-attr -a tests/fixtures/sub/bom.cpp` | `text: unset`. A product path reports `text: auto` and `eol: lf` |
| A fixture keeps its bytes into the index and back out | CRLF, BOM with CRLF, cp1250, lone-CR and mixed probes staged, then compared with `git cat-file blob`, `git cat-file --filters` and `git checkout-index` after a delete | 5 of 5 byte-identical. `git ls-files --eol` shows `i/crlf` and `i/mixed` |
| The same bytes outside `tests/fixtures/` are converted | The same five probes in `tests/probe-control/` | 4 of 5 come back LF. The lone-CR probe stays as written, because git classes it as not text (`i/-text`) |

The plugin skeleton from a local marketplace, checked on 2026-09-27 with the `claude` CLI 2.1.283, after task 02:

| Claim | Test | Result |
|---|---|---|
| A manifest with no `version` validates | `claude plugin validate .` and `claude plugin validate plugins/io-guard` | Exit 0, "Validation passed with warnings", one warning each: "No version specified". `--strict` exits 1, so CI runs without it while D18 holds |
| A local marketplace is a `directory` source | `claude plugin marketplace add <this clone>` | "declared in user settings": `extraKnownMarketplaces.claude-io-guard` in `~/.claude/settings.json`, and an entry in `~/.claude/plugins/known_marketplaces.json` |
| An install with no `version` tracks the commit | `claude plugin install io-guard@claude-io-guard`, then `claude plugin list` | `Version: 87246a2a7012`, the HEAD commit, while the plugin's own files were still uncommitted |
| A `userConfig` default counts as not set | The same install | "1 userConfig option not yet set", although `python` has the default `python3` |
| The stub skill loads | `claude plugin details io-guard` | Skills (1) `io-guard`, about 109 tokens in every session |

## Doc facts, checked on 2026-09-27

| Fact | Source |
|---|---|
| PreToolUse `updatedInput` replaces the tool's input before the tool runs, and permission rules are evaluated against the updated input. It combines with `allow` to auto-approve, or with `ask` to show the modified input to the user (re-read by Fable on 2026-09-27, where an earlier reading said `allow` only) | https://code.claude.com/docs/en/hooks |
| Exec-form hooks (`args` present) run without a shell. Shell form runs `sh -c` on macOS and Linux, Git Bash on Windows, PowerShell when Git Bash is missing | https://code.claude.com/docs/en/hooks |
| `PostToolUseFailure` and `FileChanged` events exist. Hook handlers can be `command`, `http`, `mcp_tool`, `prompt` or `agent` | https://code.claude.com/docs/en/hooks |
| Checkpoints track only Claude's file editing tools. "Checkpointing does not track files modified by Bash commands." Symlinked and hard-linked paths are not restored | https://code.claude.com/docs/en/checkpointing |
| "As a deny rule, both forms remove the tool from Claude's context" (bare `Bash`) | https://code.claude.com/docs/en/permissions |
| Settings skip "any `mcp__` rule that has parentheses". `PowerShell(...)` rules match like Bash rules | https://code.claude.com/docs/en/permissions |
| A plugin's `settings.json` applies only `agent` and `subagentStatusLine`. "every other key is dropped", so no permissions and no `env` | https://code.claude.com/docs/en/plugins/components |
| `${CLAUDE_PLUGIN_ROOT}` is substituted in hook and MCP `command`, `args` and `env`. It points at a version directory. Durable files go in `${CLAUDE_PLUGIN_DATA}` | https://code.claude.com/docs/en/plugins/components, /plugins/loading |
| `${user_config.KEY}` is substituted in MCP server config, exec-form hook `args`, and skill and agent content. A shell-form hook `command` rejects it, and the component fails instead of running. Every option also reaches hook processes as `CLAUDE_PLUGIN_OPTION_<KEY>`. A `userConfig` option is a strict object: `type`, `title` and `description` are required, and an unknown key stops the plugin loading | https://code.claude.com/docs/en/plugins-reference |
| Only npm and Bun lockfiles get their dependencies installed. Python dependencies do not | https://code.claude.com/docs/en/plugins/loading |
| Component paths with a backslash fail on macOS and Linux. Use forward slashes | https://code.claude.com/docs/en/plugins/loading |
| A top-level `bin/` makes Chat and Cowork refuse the whole plugin | https://claude.com/docs/plugins/platform-support |
| Chat ignores hooks and local MCP servers. Cowork and Claude Code load them | https://claude.com/docs/plugins/platform-support |
| A plugin enabled on the claude.ai account loads in Claude Code as `<name>@synced`, hooks and MCP servers included, "with the same trust as a marketplace plugin you installed". Terminal sync needs Claude Code 2.1.273 or later | https://code.claude.com/docs/en/plugins/loading |
| Auto-update is on by default for marketplaces added from claude.ai, off for others. Omitting `version` makes installs track commits | https://code.claude.com/docs/en/plugins/loading, /plugins/host-marketplace |
| Plugin files must stay out of Git LFS: clones get pointer files | https://code.claude.com/docs/en/plugins/host-marketplace |
| MCP output: 25,000 tokens by default, a warning at 10,000, overflow saved to a file. MCP tools sit behind tool search by default. An MCP call still running after 2 minutes moves to the background | https://code.claude.com/docs/en/mcp |
| The sandbox runs on macOS, Linux and WSL2. "Native Windows is not supported." It wraps Bash, PowerShell and Monitor | https://code.claude.com/docs/en/sandboxing |
| Issue #92543, open since 2026-09-06: the Bash tool's `bash.exe -c` argument is cut between 8,181 and 8,190 characters and every `\\` is halved, because libuv quotes by MS-CRT rules and MSYS2 re-reads them. Suggested fix: hand the script to bash through a file or stdin | https://github.com/anthropics/claude-code/issues/92543 |
| Issue #95653, closed 2026-09-20: plugin `bin/` PATH entries were inlined into the same `bash -c` string and ate the budget | https://github.com/anthropics/claude-code/issues/95653 |

## MCP 2026-07-28 ("MCP 2.0") and its extensions, checked on 2026-09-27

| Fact | Source |
|---|---|
| The core is stateless. Every request carries `_meta` with `io.modelcontextprotocol/protocolVersion` and `io.modelcontextprotocol/clientCapabilities` (both required) and `clientInfo`. A request missing a required field gets `-32602` | https://modelcontextprotocol.io/specification/2026-07-28/basic |
| Servers MUST implement `server/discover`, which returns `supportedVersions`, `capabilities`, `serverInfo`, `ttlMs` and `cacheScope`. An unsupported version gets `UnsupportedProtocolVersion` (`-32022`) with the supported list | https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning |
| A dual-era server MAY serve legacy `initialize` clients and modern clients at once. A stdio client probes with `server/discover` and falls back to `initialize` | same |
| Every result carries `resultType`: `complete`, or `input_required` for a multi round-trip request that asks the user through `elicitation/create` and resumes with `inputResponses` and `requestState` | https://modelcontextprotocol.io/specification/2026-07-28/server/tools |
| State across calls lives in explicit handles returned by a tool: opaque (such as a UUIDv4), with a lifetime stated in the tool description, and an expired handle is a tool execution error | same |
| A tool has `name` (dots allowed), `title`, `description`, `inputSchema` (JSON Schema 2020-12), `outputSchema`, `annotations` and `icons`. `structuredContent` must match `outputSchema`, and a text copy stays for older clients. `tools/list` is ordered the same every time, and carries `ttlMs` and `cacheScope` | same |
| Tool execution errors are results with `isError: true` and actionable text. Protocol errors are JSON-RPC errors. New error codes live outside `-32768` to `-32000` | https://modelcontextprotocol.io/specification/2026-07-28/basic |
| `_meta` may carry OpenTelemetry `traceparent`, `tracestate` and `baggage` | same |
| Stdio servers take credentials from the environment and do not follow the HTTP authorization spec | same |
| Extensions are opt-in per request: the client lists them in `clientCapabilities.extensions`, the server in `server/discover` | https://modelcontextprotocol.io/extensions/overview |
| MCP Apps (`io.modelcontextprotocol/ui`): a tool's `_meta.ui.resourceUri` names a `ui://` resource holding HTML (`text/html;profile=mcp-app`), rendered in a sandboxed iframe that talks to the host over postMessage. A server keeps returning meaningful text for clients without the extension | https://modelcontextprotocol.io/extensions/apps/overview |
| Clients with MCP Apps: Claude (web) and Claude Desktop, among others. Claude Code is not listed. Tasks and Skills over MCP have no Claude client listed. Enterprise-Managed Authorization serves enterprise IdPs over HTTP | https://modelcontextprotocol.io/extensions/client-matrix |
| Claude Code has two MCP client runtimes. The v2 runtime (TypeScript SDK 2.0) speaks 2026-07-28 with HTTP servers that support it, and connects to stdio servers the legacy way unless `MCP_PROTOCOL_NEGOTIATION=auto`. `MCP_SDK_GENERATION` picks the runtime | https://code.claude.com/docs/en/mcp |

## Not verified yet (task 03)

- `bashEditDiff` in the PostToolUse input for Bash, and the setting that enables it.
- `CLAUDE_ENV_FILE` for SessionStart hooks.
- PostToolUse `updatedToolOutput` and `classifierContext`.
- Whether `updatedInput` on a Bash or Write call runs the rewritten input on this harness, and whether a Write `content` holding `\r\n` lands byte-exact.
- Whether the desktop app's Code tab loads synced plugins. The docs name Cowork and terminal sessions.
- How claude.ai reaches a private repository added for oneself.
- `${user_config.*}` in a hook's `command`. The docs say a shell-form `command` rejects it (Doc facts).
- Whether `${user_config.python}` resolves to its `default` when the user never set it. `claude plugin install`
  reports the option as not yet set. Task 06 depends on the answer.
- The Bash tool's behaviour on macOS. Expected: no halving and no 8 KB limit, because no MS-CRT quoting is involved.
  Waits for the Mac (D21), and so does `bash --version` through the Bash tool there.
- Whether an `mcp_tool` hook can pass the whole hook event to a tool on the plugin's own MCP server. If it can,
  one long-lived process serves the hooks and the tools, with no Python start-up per call (D13). The docs promise
  string `${path}` substitution in `input` and nothing more, so record what an absent field, a boolean and an object
  become (`${tool_input.replace_all}`, `${tool_input.content}`), and whether a hook-invoked MCP tool prompts.
- Whether `ask` with `updatedInput` shows the rewritten command to the user, and whether a hook `allow` skips the
  auto-mode classifier (D12).
- Whether `io.*` calls prompt in manual mode, and whether `readOnlyHint` changes that.
- What the session shows when the io server is down: the `hook error` notice.
- Which protocol era Claude Code (desktop and CLI) uses with the io server, with and without
  `MCP_PROTOCOL_NEGOTIATION=auto`, and whether it answers `input_required`, renders MCP Apps, or declares the Tasks
  extension.

## Baseline

738 transcripts (6.4 GB, main sessions and sub-agents, 2026-06-20 to 2026-09-27) and 1,819 scratchpad scripts.
Counts are per call. Task 31 re-measures against these.

| Measure | Count |
|---|---|
| Tool calls | Bash 97,579, PowerShell 5,565, Edit 26,098, Write 10,920, Read 27,858, Grep 8,894, Glob 938 |
| Edit errors | 71 not found, 62 not read yet, 16 modified since read, 16 classifier unavailable, 8 missing path, 5 rejected, 3 EPERM, 2 identical strings, 1 multiple matches |
| Write errors | 39 modified since read, 20 not read yet, 1 invalid input |
| Read errors | 53 missing path, 15 token limit, 5 size limit, 8 invalid JSON |
| Grep and Glob errors | 163 missing path, 7 rejected pattern, 4 timeouts |
| Bash "unexpected EOF" | 236: 201 waiting for `'`, 16 for `"`, 11 for a backtick, 7 for `)` |
| Heredoc failures by command size | Under 6 KB: 2 of 19,698. 6 to 8 KB: 32 of 222. 8 to 16 KB: 160 of 160. Largest pass 7,810 bytes, smallest failure 7,807, each apostrophe counted as 4 bytes |
| Cost of failed long commands | 241 commands, 2.0 MB, about 531k tokens |
| Other shell results | 97 invalid-escape warnings, 8 unicodeescape errors, 34 charmap + 4 decode + 6 ascii errors, 37 MSYS conversions, 432 git "LF will be replaced by CRLF" warnings, 180 "Output too large", 5,669 cwd resets, 12 guard refusals (1 false) |
| Shell writes | 20,646 commands carry a heredoc, 15,129 run `python -c` (most only read), 907 `sed -i`, 5,114 redirects into a source-type file, 196 Set-Content, Out-File or WriteAll*, 118 here-strings |
| Scratchpad scripts | 1,819 (6.6 MB). 417 write files (2.9 MB, about 759k tokens). `edit()` defined in 138 scripts in 73 bodies. 306 read with `newline=''`. 194 assert one match. 117 splice between `str.index` markers. 70 refuse non-ASCII |
| Most-run helpers | `tlog.py` 420 runs (append), `fmt_hunks.py` 197 (format changed lines), `logcheck.sh` 54 (new log lines), `endings.py` 40 (count endings) |
| What Bash was used for | 54% of calls run Python, 16.5% only inspect, 13.5% change files, 7.3% wait or manage processes, 5.5% git, 3.6% build or editor runs |

## Failure catalog and the task that covers each

Classes: **data** leaves a file or result wrong, **time** costs retries and tokens, **noise** is friction. Scope:
**win** happens on Windows only, **all** everywhere. "-" means not planned, because it is outside file and shell IO.

| Id | Title | Class | Scope | Task |
|---|---|---|---|---|
| ANC-1 | Anchor not found | time | all | 20, 24 |
| ANC-2 | Anchor matches more than once | data | all | 20, 24 |
| ANC-3 | A batch stops half applied | data | all | 24 |
| ANC-4 | Trailing whitespace is cut from new_string | data | all | 17, 18 |
| ANC-5 | Private-use glyphs are invisible | data | all | 15, 18 |
| STL-1 | File changed between read and write | time | all | 20, 21 |
| STL-2 | Edit or Write before Read | noise | all | 20 |
| STL-3 | Someone else edits the same tree | data | all | 10, 19 |
| STL-4 | Edit with identical strings | noise | all | 20 |
| BYT-1 | Write turns a CRLF file into LF and drops its BOM | data | all | 17, 18 |
| BYT-2 | Scripts rewrite every line ending | data | all | 12, 21 |
| BYT-3 | A formatter leaves mixed endings | data | all | 18, 26, 30 |
| BYT-4 | Read hides endings, BOM and encoding | time | all | 16 |
| BYT-5 | Git Bash tools misreport CR | time | win | 15 |
| BYT-6 | Non-UTF-8 bytes become U+FFFD | data | all | 15, 18 |
| BYT-7 | BOM lost or added | data | all | 17, 18 |
| BYT-8 | PowerShell changes bytes on write, redirect and pipe | data | win | 12 |
| BYT-9 | A file is cut to 0 bytes | data | all | 12, 24, 32 |
| BYT-10 | Rebuilt versions must keep the index bytes | data | all | 32 |
| BYT-11 | Indent style does not match the file | noise | all | 17, 18 |
| BYT-12 | Whole-file rewriters change more than asked | noise | all | 26 |
| BYT-13 | Non-ASCII slips into ASCII-only files | noise | all | 18 |
| SHW-1 | Files changed by shell instead of the edit tool | data | all | 12 |
| SHW-2 | The Bash tool halves backslashes, even in a quoted heredoc | data | win | 11, 13 |
| SHW-3 | A regex loses a backslash and silently matches nothing | data | win | 11, 13 |
| SHW-4 | Commands over about 7.8 KB fail | time | win | 10, 11 |
| SHW-5 | Backticks run as commands | data | all | 13 |
| SHW-6 | Python escape errors in inline scripts | time | all | 13 |
| SHW-7 | A trailing backslash escapes the closing quote | time | all | 13 |
| SHW-8 | The write guard refuses a harmless command | noise | all | 09, 12 |
| VFY-1 to VFY-5 | Formatter, parse, lint and type checks after an edit | time | all | 18 |
| VFY-6 | Proving a comment-only pass changed no code | time | all | 32 |
| VFY-7 | The result came from an old binary | data | all | 22 |
| PTH-1 | Guessed path does not exist | time | all | 20 |
| PTH-2 | The working directory resets after cd | noise | all | 14 |
| PTH-3 | A write lands in another checkout | data | all | 19 |
| PTH-4 | Git Bash rewrites arguments that start with a slash | time | win | 14 |
| PTH-5 | Reserved Windows names | data | win | 14, 19 |
| SHL-1 | Shell dialect sent to the wrong tool | time | win | 13 |
| SHL-2 | Python prints through the Windows code page | time | win | 10, 13 |
| SHL-3 | Interpreter or tool not found, or the wrong one | time | all | 06, 10 |
| SHL-4 | PowerShell parse traps | time | win | 13 |
| SHL-5 | PowerShell cmdlet and variable traps | time | win | 13 |
| SHL-6 | PowerShell splits -name:value arguments | time | win | 13 |
| SHL-7 | PowerShell 7 syntax in scripts meant for 5.1 | time | win | 18 |
| SHL-8 | cmd and batch quirks | time | win | 14 |
| SHL-9 | A TMP override leaks into child tools | noise | all | 14 |
| SHL-10 | A define lost its quotes in a response file | time | all | - |
| SHL-11 | Text matching picked the wrong XML block | time | all | - |
| OUT-1 | A pipe or chain hides the real exit code | data | all | 13, 22 |
| OUT-2 | A filter cuts the lines that matter | data | all | 22, 25 |
| OUT-3 | Exit code 1 that is not an error | noise | all | 22 |
| OUT-4 | Tool output in the system language | time | win | 10 |
| OUT-5 | Mojibake in output | noise | win | 10, 22 |
| OUT-6 | The summary line is missing from test output | time | all | - |
| OUT-7 | Log searches raise false alarms | noise | all | 22 |
| OUT-8 | A wrong guess about output structure | time | all | 25 |
| OUT-9 | Locale number and name formats | noise | all | - |
| OUT-10 | Long output is saved to a file the agent must read again | time | all | 22, 25 |
| OUT-11 | A growing log needs a "new lines since" reader | time | all | 25 |
| RUN-1 | sleep chains are blocked | time | all | 27 |
| RUN-2 | Background output read before the run ended | data | all | 25 |
| RUN-3 | Broad searches time out | time | all | 20 |
| RUN-4 | Commands hit the ten-minute cap | time | all | 25 |
| RUN-5 | A silent long run looks hung | time | all | - |
| RUN-6 | A script edited while a run used it | data | all | 25 |
| LCK-1 | Edit fails because the file is locked | time | win | 19, 20 |
| LCK-2 | Build output locked by a running program | time | win | - |
| LCK-3 | Killing by name hits the user's programs | data | all | - |
| LCK-4 | A read-only file blocks the write, or hangs the editor | time | all | 19 |
| GRD-1 | A guard reads a path out of other tokens | time | all | 12 |
| GRD-2 | The auto-mode classifier refuses or is down | time | all | - |
| GRD-3 | The user stops the action | time | all | - |
| GIT-1 | Scratch files inside the repository | data | all | 12 |
| GIT-2 | A command created files | time | all | 21 |
| GIT-3 | Broad staging | data | all | - |
| GIT-4 | No record of which edit belongs to which change | time | all | 32 |
| GIT-5 | Shared stash across worktrees | data | all | - |
| GIT-6 | Whole-file undo loses other edits | data | all | 32 |
| GIT-7 | git status lists files that did not change | noise | all | 21 |
| GIT-8 | Commit rules | time | all | - |
| GIT-9 | Junk in the staged diff | data | all | 18 |
| INP-1 | Tool input that is not valid JSON | time | all | - |
| INP-2 | MCP call shape errors | time | all | - |
| INP-3 | File too big for one Read | noise | all | 20 |
| INP-4 | Read refuses a text file as binary | time | all | 20, 24 |
| INP-5 | Grep pattern rejected | time | all | 20 |
| EXT-1 to EXT-7 | Test-helper rows from the friend's scan | - | all | - |

macOS brings its own candidates, not measured yet: `/bin/bash` 3.2 against Git Bash 5 (`readarray`, `${x,,}`),
BSD `sed -i ''`, `stat -f` and no `grep -P`, NFD file names on APFS, and case-insensitive paths. Task 36 covers them
once the Mac is back (D21).

## What the repositories look like (why every check reads the file's own convention)

Surveyed on 2026-09-27, every tracked text file.

| Repository | Config | C++ endings CRLF / LF / mixed | C++ with BOM | C++ indent tab / space / both | Markdown CRLF / LF |
|---|---|---|---|---|---|
| CLICKER | autocrlf=true. clang-format UseTab: Never | 2,541 / 102 / 0 | 5 | 926 / 1,360 / 237 | 2 / 23 |
| OrbitalDrift | autocrlf=true. .editorconfig tabs, crlf. clang-format UseTab: Always, LineEnding: CRLF | 2,286 / 0 / 0 | 31 | 1,323 / 589 / 253 | 14 / 0 |
| SmartTablesHost | autocrlf=true. clang-format UseTab: Never, LineEnding: CRLF | 217 / 0 / 0 | 0 | 0 / 206 / 0 | 23 / 37 |
| UNREAL-SHARED | autocrlf=true. clang-format UseTab: Always, LineEnding: CRLF | 0 / 74 / 0 | 0 | 71 / 0 / 0 | 1 / 183 |

## Error codes (draft, task 07 fixes the final list in `lib/results.py`)

`docs/design/architecture.md`, section 2, adds `REWRITE_CONFLICT`, `BUDGET_EXCEEDED`, `HANDLE_EXPIRED`,
`RULE_DENIED`, `RULE_ASKED`, `SERVER_DOWN` and `CANCELLED` to the list below.

Every result the guard returns has this shape:

```json
{"ok": false, "code": "ANCHOR_AMBIGUOUS", "severity": "refused", "tool": "Edit", "platform": "win32",
 "file": "C:/.../X.cpp", "message": "old_string matches at lines 41 and 208.",
 "evidence": {"eol": "crlf", "bom": true, "matches": [{"line": 41, "context": "..."}]},
 "fix": {"tool": "Edit", "input": {"old_string": "<shortest unique anchor>", "new_string": "..."}},
 "auto_fixed": []}
```

`severity` is `fixed` (the call ran after a mechanical fix, listed in `auto_fixed`), `refused`, or `warning`.

| Layer | Codes |
|---|---|
| Transport | `BODY_MOVED_TO_FILE`, `TRANSPORT_BUDGET`, `BACKSLASH_TRANSPORT`, `BACKTICK_IN_DOUBLE_QUOTES`, `TRAILING_BACKSLASH_QUOTE`, `MSYS_PATH`, `RESERVED_NAME`, `DIALECT_MISMATCH`, `SHELL_WRITE`, `PIPE_HIDES_EXIT`, `INLINE_SCRIPT_INVALID` |
| Bytes | `EOL_CONVERTED`, `EOL_MISMATCH`, `BOM_RESTORED`, `BOM_CHANGED`, `ENCODING_INVALID`, `TRAILING_WS_STRIPPED`, `INDENT_MISMATCH`, `NON_ASCII_ADDED`, `CONTROL_BYTES_ADDED`, `SIZE_COLLAPSED`, `UNINTENDED_CHANGE` |
| Location | `OUTSIDE_WRITE_ROOT`, `LINKED_PATH`, `READ_ONLY`, `FILE_LOCKED` |
| Stale view | `ANCHOR_NOT_FOUND`, `ANCHOR_AMBIGUOUS`, `STALE_VIEW`, `NOT_READ`, `TOUCHED_BY_SHELL` |
| Read | `PATH_NOT_FOUND`, `READ_TOO_LARGE`, `PATTERN_INVALID`, `SEARCH_TOO_BROAD` |
| Output | `EXIT_BENIGN`, `OUTPUT_SAVED`, `ERRORS_IN_OUTPUT`, `MOJIBAKE` |
| Internal | `GUARD_ERROR` |
