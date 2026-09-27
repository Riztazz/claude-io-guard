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
| D24 | A project's `io-guard.json` never makes io-guard run a program. `verify` commands come only from the user's `config.json`, where a command for one project is keyed by the project's root. Set on 2026-09-27, when the lead asked for the security issue raised in task 07 to be handled | A cloned repository must not execute code through the guard (`architecture.md`, section 12), and the design's first draft let a project file add `verify` commands, which io-guard would run on every write |
| D25 | A body io-guard moves into a file arrives byte-exact, with no backslash halved. A halving pair left outside a moved body is a `BACKSLASH_TRANSPORT` warning, and the call runs. Set on 2026-09-27 by the lead during task 11, choosing the plan's exact bytes over keeping the halving | Replay over 180,464 calls: refusing a pair outside a body would stop 971 calls that ran, 1.0%, because agents double backslashes to survive the halving. Of 20 sampled passing calls an exact move changes, 12 had been silently corrupted by the halving and are fixed, 4 had doubled on purpose and break, and 4 read the same. Anthropic's fix to #92543 breaks the doubling anyway |
| D26 | A rewrite of an Edit or Write input answers `updatedInput` with no `permissionDecision`, so the harness asks or approves as it would have for the original call. A check's own ask or deny still outranks it. Set on 2026-09-27 in task 17, which asked for this answer once the harness was shown to keep its own decision ("Hooks and MCP", row 27) | An `allow` would skip the prompt for a write outside the working directory, or in default mode, that nobody approved. The rewrite restores only the file's own endings, BOM and indent, and the prompt shows the input as it will land |
| D27 | io-guard has no write-roots rule, and refuses no Edit or Write for landing outside the project. `OUTSIDE_WRITE_ROOT` and `write_roots.extra` left the plan. Chosen by the lead on 2026-09-27 in task 19, over refusing only another checkout of the same repository, refusing with an extra root in the lead's config, and warning on every such write | Replay over 23,734 recorded Edit and Write calls: 880 (3.7%) landed in another repository or in a folder outside any, 610 of them in auto mode, and almost all on purpose, such as a kit task filed from a game project. Another checkout of the same repository (PTH-3) came to 13, all from a session whose folder was a junction. Claude Code already prompts for a write outside the working folder in default and acceptEdits modes |
| D28 | An Edit or Write that Claude Code refuses before its hooks run is diagnosed at the session's next hook, from the end of the transcript, once per refused call. Chosen by the lead on 2026-09-27 in task 20, over leaving anchor misses to `io.edit` (task 24) and over a task of its own | Those refusals reach no hook ("Hooks and MCP", row 30), and they are the 67 anchor misses task 20 exists for. The model's next call is usually a Read of the same file, so the diagnosis lands before the retry. The transcript is Claude Code's own file, in a format it does not document, so `live-diagnose` checks it after each release |

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
| A trailing space asked for in new_string does not reach the file | new_string `one = ` | `one =`. Task 17 found the space already gone from the model's own `tool_use`, before any hook. The Edit tool keeps one it is given (Hooks and MCP, row 28) |
| Write writes LF over a CRLF file | Write `alpha`, `beta` | `alpha\nbeta\n` |
| Write drops a BOM | The same Write over a BOM file | No BOM |
| Read hides endings and BOM | Read of CRLF, LF and CRLF-with-BOM probes | Three identical outputs |
| Python prints through cp1252 | `print()` of U+2192 | `UnicodeEncodeError: 'charmap' codec can't encode character '\u2192' in position 22: character maps to <undefined>` |

The probes are `baseline/eol_probe.py`.

Task 13 checked, through the PowerShell tool on PowerShell 7.6.6, the PowerShell calls `shell.lint` refuses: an
assignment to one of 12 read-only automatic variables such as `$PID` or `$HOME`, `Select-String -Recurse`,
`export`, and `> /dev/null` on Windows. A `pwsh` start that parses one command takes 191 to 218 ms, so the check
parses PowerShell itself rather than through `pwsh`. `docs/live-checks.md` has each error text.

Task 14 checked Git Bash 5.2.37 through this session's Bash tool: a slash argument for a Windows program
becomes a path under Git's install folder, a lone `/F` becomes `F:/`, and `/p:x` loses its slash.
`MSYS2_ARG_CONV_EXCL` keeps the prefixes it names while `/c/...` and `/tmp/...` still convert, and
`MSYS_NO_PATHCONV=1` stops all of them. `cmd /c` runs nothing, and `2>nul` writes a real file named `nul`.

Task 16's `live-read-profile` probe passed on the desktop's 2.1.281 and the CLI 2.1.283: after a Read of a
BOM and CRLF file, the model quoted "PostToolUse:Read hook additional context: io-guard: CRLF, BOM, UTF-8,
tabs, 2 lines". The check adds 12.8 ms after a Read of a 1 MB file.

Task 17's probes passed on the desktop's 2.1.281 and the CLI 2.1.283. `live-conform` read a BOM and CRLF
`keep.txt` and wrote two lines over it in acceptEdits, with io-guard loaded, and the file landed as `EF BB BF`
then `gamma\r\ndelta\r\n`. `write-quiet` is "Hooks and MCP", row 27, and `edit-trailing` is row 28.

Task 18's `live-verify` and `live-verify-direct` passed on both releases ("Hooks and MCP", row 29), and
`live-empty` and `live-conform` still pass with `verify.write` and `verify.command` loaded. `verify.write`
takes 0.8 ms before and 6.4 ms after an Edit of a 0.1 MB file, 8.1 and 66.9 ms at 1 MB, and 15.4 and 32.0 ms
at 2.15 MB, where the file is past `snapshot_bytes` and only the profiles are compared (p50 of 5).

Task 19's `live-read-only` and `live-locked` passed on both releases. An Edit of a read-only file that git marks
lockable was refused with `READ_ONLY: Hero.uasset is read-only. Lock it with git lfs lock Hero.uasset from the
repository root, then call Edit again.` An Edit of a file another process held open, sharing reads only, failed
with the baseline's `EPERM: operation not permitted, rename '<file>.tmp.<n>' -> '<file>'`, and the model saw
`FILE_LOCKED: Python (process 42544) holds keep.txt open`. The same Edit succeeded while the holder shared reads
and writes, which is how Python's `open` holds a file. The Restart Manager names a holder in 95 to 104 ms.

Task 20 replayed `anchors.closest` over the recorded anchor misses. The corpus holds 78, and 67 of them were found
in the transcripts. For 25 of those the model later edited the same file, and that Edit's `originalFile` is the
file as it was and its `old_string` the region meant: `closest` named that region first for 19 (76%). Over every
transcript on the machine the numbers are 133 misses, 39 judged and 27 named (69%). `closest` took 4.3 ms at p50
and 51 ms at most. The first version matched with a regular expression that backtracked for 2.6 s on one miss.

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

The launcher, checked on 2026-09-27 during task 06, with io-guard installed from the local marketplace and one
headless session per case (`docs/launcher.md`):

| Claim | Test | Result |
|---|---|---|
| `.mcp.json` and `hooks.json` start the stub server and the hooks | `python` set, the CLI 2.1.283 and the desktop's 2.1.281 | The server connected in 67 to 69 ms in the legacy era. SessionStart ran through `hook.sh`, and the `mcp_tool` hook recorded the Bash and Read calls |
| A dotted tool name works in an `mcp_tool` hook | `hook.pre_tool_use` | Called on both versions |
| `${CLAUDE_PLUGIN_DATA}` substitutes in `.mcp.json` `env` | The stub server's `IOGUARD_DATA` | It wrote into the plugin data folder |
| An unset `userConfig` option falls back to its `default` | Installed with no `--config` | The server ran `python3`, the Store stub: "Python was not found; run without arguments to install from the Microsoft Store" |
| `CLAUDE_PLUGIN_OPTION_PYTHON` reaches a command hook | `python` set to `io-guard-no-such-python` | `hook.py` quoted that value in its warning |
| On Windows the harness starts an MCP server's command through `cmd.exe` | The same wrong setting | Server stderr: "'io-guard-no-such-python' is not recognized as an internal or external command, operable program or batch file." |
| A server that never started: every hooked call gets its own notice | The same wrong setting | Each PreToolUse hook answered `MCP server 'plugin:io-guard:io' not connected`, non-blocking, and both tool calls ran |
| Hook paths, 100 Bash calls each on the CLI 2.1.283 | `launch-mcp`, `launch-exec`, `launch-hooksh` | `mcp_tool` p50 1.2 ms, p95 1.6 ms. Exec form 53.4 and 58.0 ms. Through `hook.sh` 129.8 and 139.1 ms |

The hook entry point, checked on 2026-09-27 during task 08 with Haiku 4.5, on the CLI 2.1.283 and again on the
desktop's bundled 2.1.281, where every verdict passed too. Each run loads io-guard from this checkout with
`--plugin-dir` and row 21's setting, and `tests/support/inject` on `PYTHONPATH` adds the test checks the run
names (`tools/probes/run_probe.py`, the `live-*` probes):

| Claim | Probe | Result |
|---|---|---|
| The empty pipeline answers every guarded call | `live-empty` | Bash, PowerShell, Write, Read, Edit and a Read of a missing file ran. 13 hook answers, all `success`. Telemetry: 1 SessionStart, 6 PreToolUse, 5 PostToolUse and 1 PostToolUseFailure line, surface `mcp_hook` for the tool events |
| A broken check leaves the session working (D7) | `live-broken` | The same six calls ran, and `w.txt` ended as `ONE`. 13 `GUARD_ERROR` lines, and the other check's context reached the model on every event. The warning showed twice, once from the SessionStart command hook and once from the server, which are two processes |
| Each answer shape works | `live-answers`, bypassPermissions | The rewrite answered `allow` with `updatedInput`, and Bash printed `IOGUARD_REWRITTEN`. The refusal's reason reached the model as `PreToolUse:Bash hook error: GUARD_ERROR: io-guard's test check refused this command. Run echo IOGUARD_ALLOWED instead.` |
| Refuse mode gives the model the command to run | `live-refuse`, dontAsk | The deny carried `Run this command instead, exactly as written:` and the rewritten command. The model ran it next, once |

### Hooks and MCP

Checked on 2026-09-27 with the probes in `tools/probes/`, task 03: `claude -p` 2.1.283 with Haiku 4.5 (Sonnet 5 for
auto mode, which Haiku disables), and the desktop app's Code tab on its bundled 2.1.281. The column names each
probe in `tools/probes/run_probe.py`. Hook times run from the stream's `hook_started` line to its `hook_response`.
Task 05 keeps one recorded event per kind, scrubbed of local paths and ids, in `tests/fixtures/events/`, and
`tests/support/events.py` builds events with the same fields. A SessionStart event carries `source`, such as
`startup`, and no `permission_mode` or `prompt_id`. A PostToolUse or PostToolUseFailure event adds
`duration_ms`, and a failure adds `error` and `is_interrupt`.

Task 04 reran every probe on the desktop app's bundled `claude.exe` 2.1.281 and on the CLI at 2.1.283, and the
runner's `verdicts` command passed all 28 on both. One 2.1.283 run of `mcp-prompts` first failed its verdict:
the model stopped asking after the first denial, so the verdict now checks that every probe tool called was
denied, and the rerun denied all three. Ten calls each took:

| Form | 2.1.281 p50 / p95 | 2.1.283 p50 / p95 |
|---|---|---|
| exec | 57.1 / 73.7 ms | 59.6 / 72.6 ms |
| shell through Git Bash | 89.7 / 111.0 ms | 92.5 / 99.9 ms |
| `mcp_tool` | 1.5 / 1.7 ms | 1.3 / 1.8 ms |

| # | Claim | Probe | Result |
|---|---|---|---|
| 1 | PreToolUse `updatedInput` with `allow` runs the new input | `rewrite-allow` | Bash printed `IOPROBE_REWRITTEN`. The model's own `tool_use` keeps the original command, and its result is only the output |
| 2 | A Write `content` rewritten by a hook lands byte-exact | `write-bytes` | `﻿line one\r\nline two\r\n` landed as `EF BB BF` and CRLF, byte for byte. The model sees only "File created successfully" |
| 3 | An Edit with both strings extended by one character runs | `edit-extend` | The edit ran on the extended anchor, and the file became `alpha BETA gamma\n` |
| 4 | PostToolUse `additionalContext` on Read reaches the model | `read-context` | The model quoted `PostToolUse:Read hook additional context: <text>` |
| 5 | What PostToolUseFailure sees | `failures` | A missing Read path and Bash `exit 3` fire it, with `error` "File does not exist. Note: your current working directory is <cwd>." and "Exit code 3". Its `additionalContext` reaches the model as a system reminder. An Edit whose `old_string` is missing fires **no hook at all**: the tool refuses before it runs, with `<tool_use_error>String to replace not found in file.\nString: <old_string></tool_use_error>`. An Edit after the file changed on disk **succeeds**, with a note that the file was modified since it was read |
| 6 | `bashEditDiff` | `bash-diff-on`, `bash-diff-off` | Only with `bashEditDiffEnabled: true`, and inside `tool_response`: `{"files": [{"filePath", "hunks": [{"oldStart", "oldLines", "newStart", "newLines", "lines": ["-a", "+b"]}]}]}`. Absent without the setting. The probe had read the file first |
| 7 | `CLAUDE_ENV_FILE` | `env-file` | Set for a SessionStart command hook, as `~/.claude/session-env/<session>/sessionstart-hook-0.sh`. Both `export X=v` and `X=v` lines reached a later Bash call |
| 8 | `updatedToolOutput` and `classifierContext` | `updated-output` | A string for Bash is refused, and the model sees the real output: "PostToolUse hook returned updatedToolOutput that does not match Bash's output shape: reason=schema_invalid issues=invalid_type". The `tool_response` object with `stdout` replaced works. Bash's shape is `{stdout, stderr, interrupted, isImage, noOutputExpected}`. `classifierContext` is accepted |
| 9 | Exec form against shell form, ten calls each | `time-exec`, `time-shell` | Exec: p50 58.3 ms, p95 74.7 ms. Shell through Git Bash: p50 89.7 ms, p95 97.0 ms |
| 10 | A hook that crashes, times out or prints bad JSON | `hook-crash`, `hook-timeout`, `hook-badjson` | All three are non-blocking, and the Bash call ran. A crash is `outcome: "error"`, `exit_code: 1`, with the traceback as stderr. A hook past its 3 s `timeout` is cancelled at 3,188 ms. Bad JSON gives "Hook output looks like a JSON object but is not valid JSON". The model saw none of them |
| 11 | The desktop Code tab loads a local-marketplace plugin | task 02, the io-probe install | Yes. After an app restart it runs a cached copy from `~/.claude/plugins/cache/<marketplace>/<plugin>/unknown`, not the marketplace folder. Synced plugins load there too: `superpowers@synced`'s SessionStart hook and `supericons@synced`'s MCP server ran in the Code tab session that probed the desktop |
| 12 | An `mcp_tool` hook hands the event to the plugin's own server | `mcp-gate`, `time-mcp`, `mcp-subst`, `dead-server`, `dead-for-good` | Yes. Every substituted value is a string, `${tool_input}` is the whole object as JSON text, and a returned `deny` blocks the call. p50 1.4 ms, p95 3.9 ms. A hook-invoked tool never prompts. `architecture.md`, section 6, has the detail |
| 13 | `ask` with `updatedInput` shows the new input | `ask-prompt`, and the desktop by the lead | CLI: the prompt, taken through `--permission-prompt-tool`, carried `echo IOPROBE_REWRITTEN`, which ran once approved. Desktop: the prompt showed the rewritten command under the hook's `permissionDecisionReason` |
| 14 | A hook `allow` skips the auto-mode classifier | `auto-control`, `auto-allow` | Yes. Without the hook: "Slow permission decision: 17422ms for Bash (mode=auto, behavior=allow)". With it: "Hook approved tool use for Bash, bypassing permission prompt", 17 ms |
| 15 | The MCP era | `era-legacy`, `era-auto`, the desktop | CLI by default and the desktop: legacy `initialize` at `2025-11-25`. The CLI declares `roots` and `elicitation: {form, url}`, and the desktop `roots` and `elicitation: {}`. With `MCP_PROTOCOL_NEGOTIATION=auto`: `server/discover` first, then `_meta` at `2026-07-28` on every request. `MCP_SDK_GENERATION` is unset. No client declares an extension, so no Tasks and no ui. The modern client rejects a result without `resultType`, and a `tools/list` without a number `ttlMs` and a `cacheScope` of `public` or `private` |
| 16 | Elicitation, progress, Apps and structured content | `mcp-features`, `features-modern`, the desktop | Legacy `elicitation/create`: `claude -p` answers `cancel`, and the desktop answers `decline` without showing a form. Modern: a server-sent `elicitation/create` is never answered, and the call hung past 570 s. `input_required` works: the client retries with `inputResponses` and `requestState`, and `-p` answers `cancel`. Progress notifications are accepted, and the desktop showed none. No client sent `resources/read`, so no App renders. When a result has `structuredContent`, the model sees that JSON instead of the text content |
| 17 | MCP tools prompt in default mode | `mcp-prompts`, `mcp-permit` | All three prompted: no annotations, `readOnlyHint: true` and `destructiveHint: true`. The annotations change nothing |
| 18 | A dead server | `dead-server`, `dead-for-good` | A server that exits restarts on the next hook call in about 50 ms. One that cannot start gives the non-blocking `MCP server "plugin:io-probe:probe" is not connected`, the call runs, and the model sees nothing |
| 19 | `${tool_response}` and `${error}` substitute like `${tool_input}` | `guard-fields`, with io-guard's own `hooks.json` maps, task 08 | Yes. `${tool_response}` is the compact JSON text of the whole object, such as Bash's `{"stdout":"hi","stderr":"",...}`, and `${error}` the failure's text, such as `Exit code 3`. An empty `agent_id` arrives as an empty string. The maps are `tests/fixtures/fields/` |
| 20 | A large `${tool_input}` arrives whole | `guard-large`, task 08 | Yes. A Write of 145,599 bytes and 2,599 lines reached the hook as 148,340 characters of JSON text, and its `content` matched the file on disk byte for byte. Haiku first stopped at "Claude's response exceeded the 32000 output token maximum", so the probe sets `CLAUDE_CODE_MAX_OUTPUT_TOKENS` to 64000 |
| 21 | A `--plugin-dir` plugin's `userConfig` | task 08, by hand | The plugin is `<name>@inline`, and `--settings '{"pluginConfigs": {"io-guard@inline": {"options": {"python": "python"}}}}'` sets its option: the server connected. Without it, the default `python3` failed. Its data folder is `~/.claude/plugins/data/io-guard-inline` |
| 22 | PreToolUse `additionalContext` reaches the model | `live-answers`, task 08 | Yes, alone and next to `permissionDecision: "allow"`, as a `hook_additional_context` attachment in the transcript, like PostToolUse's. The model quoted a line from one |
| 23 | Whose calls `CLAUDE_ENV_FILE` reaches | `live-probe`, task 10 | Bash only. After io-guard's session probe wrote `export PYTHONUTF8=1` and `export PYTHONIOENCODING=utf-8`, Bash's `python -c "print(chr(0x2192))"` printed the arrow, and the same command under `env -u PYTHONUTF8 -u PYTHONIOENCODING` failed with cp1252's `UnicodeEncodeError`. PowerShell printed `utf8=` for `$env:PYTHONUTF8`, so the file does not reach it, yet its Python printed the arrow too. Both releases |
| 24 | A hook's environment names the Claude Code version | `live-probe`, task 10 | Yes. `AI_AGENT` is `claude-code_2-1-283_agent` on the CLI and `claude-code_2-1-281_agent` on the desktop's copy, and `CLAUDE_CODE_EXECPATH` names the desktop's `claude-code\2.1.281\claude.exe`. The SessionStart event itself carries no version |
| 25 | Which backslashes the Windows Bash tool halves | the Bash tool of this session, desktop 2.1.281, task 11 | A run of backslashes that a double quote does not follow loses half its pairs: `'a\\b'` arrived as `a\b`, a run of four as two, a run of three as two, in single quotes and in a quoted heredoc alike. A run before `"` arrives whole: `"\\"` and four before `"` in a quoted heredoc were unchanged. A `\\` before a closing `'` was halved. So Python's `"\\"` in a heredoc runs, and `r'\\d'` silently becomes `r'\d'` |
| 26 | A moved body runs through `ask` and `refuse` | `live-move-ask`, `live-move-auto`, task 11 | Default mode, Haiku: an 8,973-character `python - <<'PY'` call was answered `ask` with `updatedInput`, the permission prompt received `python - < "<file>"`, and the approved run printed 3 for `len(r"\\n")`. Auto mode, Sonnet: the call was refused with the moved command as the fix, and the rerun printed 3. CLI 2.1.283 |
| 27 | A PreToolUse `updatedInput` with no `permissionDecision` applies, and keeps the harness's own decision | `write-quiet`, task 17 | Yes. In default mode a Write rewritten to BOM and CRLF content reached the permission prompt as rewritten, and the approved file landed as `EF BB BF` then `line one\r\nline two\r\n`, byte for byte. 2.1.281 and 2.1.283 |
| 28 | The Edit tool keeps a trailing space in new_string | `edit-trailing`, and the first `live-conform` run, task 17 | Yes. A hook that set new_string to `one = ` left `one = \ntwo = 2\n` in the file, on 2.1.281 and 2.1.283. Asked for `one = `, Haiku's own `tool_use` carried `one =`, so the space is lost before any hook sees the call, and io-guard cannot restore it (2.1.283) |
| 29 | An Edit straight after io-guard put back a file's endings and BOM succeeds with no new Read | `live-verify-direct`, `live-verify`, task 18 | Yes. A Write dropped keep.txt's BOM and CRLF, `verify.write` wrote both back, and the next Edit, with no Read between, ran and left `EF BB BF` then `GAMMA\r\ndelta`. `live-verify` read the file first and landed the same. The model saw the `EOL_CONVERTED` line both times. 2.1.281 and 2.1.283 |
| 30 | Which failed file calls reach a hook | `edit-refusals`, `other-refusals`, task 20 | An Edit or Write that Claude Code rejects as a `<tool_use_error>` fires no hook at all, neither PreToolUse nor PostToolUseFailure: not read yet, `String to replace not found`, `Found 2 matches`, `No changes to make` and a missing file for Edit, and not read yet for Write. A Read over 256 KB, a pattern ripgrep rejects, a Grep path and a Glob folder that do not exist all fire PreToolUse and then PostToolUseFailure. 2.1.281 and 2.1.283 |
| 31 | `${transcript_path}` substitutes in an `mcp_tool` map, and the transcript holds a refused call | `live-diagnose`, `guard-fields`, task 20 | Yes. The transcript records the refused call's `tool_use` and a `tool_result` with `is_error` and its text in `<tool_use_error>`. At the next hook, io-guard read the end of the transcript and its diagnosis reached the model as a `hook_additional_context` attachment, for each of seven failures. 2.1.281 and 2.1.283 |

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

## Not verified yet

- How claude.ai reaches a private repository added for oneself.
- `${user_config.*}` in a hook's `command`. The docs say a shell-form `command` rejects it (Doc facts).
- The Bash tool's behaviour on macOS. Expected: no halving and no 8 KB limit, because no MS-CRT quoting is involved.
  Waits for the Mac (D21), and so does `bash --version` through the Bash tool there.
- What the desktop shows the user when the io server cannot start. The stream reports the hook's error, and the
  model sees nothing (Hooks and MCP, row 18). Nobody has looked at the desktop's notice.
- Whether the desktop prompts on an `io.*` call in manual mode. The CLI does (row 17). The desktop session that
  ran the probes was in auto mode.
- Whether Cowork renders an MCP App.
- Where a `${tool_input}` substitution stops. 145,599 bytes arrive whole (Hooks and MCP, row 20), and nothing
  larger was tried.

## Baseline

738 transcripts (6.4 GB, main sessions and sub-agents, 2026-06-20 to 2026-09-27) and 1,819 scratchpad scripts.
Task 31 re-measures against these.

**Each call counts once.** A resumed session writes its history into a new transcript, and the copies keep the
original session id, so one call can sit in several files, and several times in one. The first baseline and task
09's corpus counted every copy: on 2026-09-27 the corpus held 180,478 records for 110,379 distinct calls. Task 37
made the corpus keep each tool use id once, and the table below is recounted from the corpus it rebuilt that day.
It replaces the first baseline's numbers, which counted copies. The scratchpad script counts come from the files
on disk, so they did not change. A helper's run is a `python`, `bash` or `sh` command that names the script.

The corpus labels follow the baseline's rules, with one change. Task 12 renamed `guard-refused` to
`hook-refused`, which matches any PreToolUse hook's refusal, `PreToolUse:<tool> hook error`, rather than one
guard's text. The baseline's rule also matched `write-guard` as a file name in git status lines, diffs and
listings.

| Measure | Count |
|---|---|
| Tool calls | 110,379: Bash 58,779, PowerShell 3,321, Edit 17,370, Write 6,347, Read 17,729, Grep 6,076, Glob 757 |
| Edit errors | 67 not found, 62 not read yet, 12 modified since read, 8 missing path, 3 rejected, 3 EPERM, 2 classifier unavailable, 2 identical strings, 1 multiple matches |
| Write errors | 20 not read yet, 18 modified since read, 1 invalid input |
| Read errors | 43 missing path, 9 token limit, 2 size limit, 8 invalid JSON, 3 other |
| Grep and Glob errors | 124 missing path, 5 rejected pattern, 3 timeouts, 3 rejected by the user, 1 invalid JSON |
| Bash "unexpected EOF" | 125: 98 waiting for `'`, 17 for `"`, 5 for `)`, 2 for a backtick, 3 at the end of the file |
| Heredoc failures by command size | Under 6 KB: 2 of 10,831. 6 to 8 KB: 11 of 158. 8 to 16 KB: 77 of 77. Over 16 KB: 10 of 10, one of them `ENAMETOOLONG`. Largest pass 7,810 bytes, smallest failure 7,807, each apostrophe counted as 4 bytes |
| Cost of commands the transport failed | 122 commands failed with unexpected EOF or an unclosed heredoc: 1.0 MB, about 262k tokens at 4 bytes a token |
| Other shell results | 72 invalid-escape warnings, 10 unicodeescape errors, 26 charmap + 16 decode + 3 ascii errors, 18 MSYS conversions, 328 git "LF will be replaced by CRLF" warnings, 148 "Output too large", 3,064 cwd resets, 8 hook refusals |
| Shell writes | 11,076 commands carry a heredoc, 8,910 run `python -c` (most only read), 385 `sed -i`, 2,381 redirects into a source-type file, 110 Set-Content, Out-File or WriteAll*, 93 here-strings |
| Scratchpad scripts | 1,819 (6.6 MB). 417 write files (2.9 MB, about 759k tokens). `edit()` defined in 138 scripts in 73 bodies. 306 read with `newline=''`. 194 assert one match. 117 splice between `str.index` markers. 70 refuse non-ASCII |
| Most-run helpers | `tlog.py` 183 runs (append), `fmt_hunks.py` 128 (format changed lines), `endings.py` 107 (count endings), `logcheck.sh` 83 (new log lines) |
| What Bash was used for | 49% of calls run Python, 18.9% only inspect, 13.3% change files, 7.6% wait or manage processes, 5.6% git, 3.8% build or editor runs |

## Failure catalog and the task that covers each

Classes: **data** leaves a file or result wrong, **time** costs retries and tokens, **noise** is friction. Scope:
**win** happens on Windows only, **all** everywhere. "-" means not planned, because it is outside file and shell
IO. Two are exceptions. ANC-4's space is gone from the model's own call before any hook sees it ("Hooks and
MCP", row 28). PTH-3 went with the write-roots rule the lead dropped (D27).

| Id | Title | Class | Scope | Task |
|---|---|---|---|---|
| ANC-1 | Anchor not found | time | all | 20, 24 |
| ANC-2 | Anchor matches more than once | data | all | 20, 24 |
| ANC-3 | A batch stops half applied | data | all | 24 |
| ANC-4 | Trailing whitespace is cut from new_string | data | all | - |
| ANC-5 | Private-use glyphs are invisible | data | all | 15, 16 |
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
| PTH-3 | A write lands in another checkout | data | all | - |
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

Surveyed on 2026-09-27, every tracked text file. Task 15's `profile` reads all 5,955 of those files the same
way the survey's rules do, for endings, BOM, UTF-8, NUL, final newline, indent and trailing whitespace, with no
file that differs.

| Repository | Config | C++ endings CRLF / LF / mixed | C++ with BOM | C++ indent tab / space / both | Markdown CRLF / LF |
|---|---|---|---|---|---|
| CLICKER | autocrlf=true. clang-format UseTab: Never | 2,541 / 102 / 0 | 5 | 926 / 1,360 / 237 | 2 / 23 |
| OrbitalDrift | autocrlf=true. .editorconfig tabs, crlf. clang-format UseTab: Always, LineEnding: CRLF | 2,286 / 0 / 0 | 31 | 1,323 / 589 / 253 | 14 / 0 |
| SmartTablesHost | autocrlf=true. clang-format UseTab: Never, LineEnding: CRLF | 217 / 0 / 0 | 0 | 0 / 206 / 0 | 23 / 37 |
| UNREAL-SHARED | autocrlf=true. clang-format UseTab: Always, LineEnding: CRLF | 0 / 74 / 0 | 0 | 71 / 0 / 0 | 1 / 183 |

## Error codes

Task 07 settled the list in `docs/design/architecture.md`, section 2, with the task that adds each code.
`lib/results.py` holds a code once something produces it, and that table marks each such row "in `CODES`". The
table below is the draft the list came from.

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
