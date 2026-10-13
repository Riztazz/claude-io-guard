# File read/write failures: findings map

Goal (lead, 2026-09-27): a general read/write tool for AI agents. Every failure class that wastes tokens or
corrupts a file, with its evidence and the check the tool must run. Skill coverage does not remove an entry.

Classes: time = retries and wasted tokens, data = a file ends up wrong, noise = friction with no damage.

## Part F: the friend's findings (pasted 2026-09-27), decomposed

Sources he names: web (W1-W17), D: (D:\fort monorepo, x-trunk), svn-git, G: (A*, B*, C* measurements),
x-graph (F*, R*). His message stops at 6.5 mid-row, and 4.1 refers to a 10.1 (EPERM), so his sections 7 to
10 did not arrive.

| ID | Class | Title | Symptom | Cause | Check he proposes | His counts |
|---|---|---|---|---|---|---|
| F1.1 | time | Anchor not found | "String to replace not found" (Edit), AssertionError / ValueError substring not found (scripts). 8 vs 6 spaces before </ul>, a one-line text written wrapped, comments left out, LF file with a CRLF anchor | G's 72 Edit misses: 30 text known only from the agent's own earlier edit (22 with a shell write after), 27 text not in the last Read, 8 file never read, 4 matched only the first line, 3 spacing. Long anchors fail as often as short. Scripts: \n anchor on CRLF file, BOM read without utf-8-sig, an earlier patch removed a later anchor | Freshness gate. On a miss show the closest whitespace-normalised match with line numbers and visible whitespace (space, tab, CR, BOM, private-use). Convert the anchor to the file's ending | web W1 W4, D: 32 Edit ~15 script, svn-git 9 Edit 34 script, G: A1 72 B1 186 |
| F1.2 | data | Anchor matches more than once | "Found 2 matches of the string to replace, but replace_all is false." A script replacing the first match edits the wrong place | Short or common anchor | List every match with 2 lines of context, propose the shortest unique anchor. Scripts assert exactly one | web W2, D: 3, svn-git 1, G: A2 16 |
| F1.3 | data | Batch half-applied | 3-edit script wrote 1-2, failed on 3. git diff was the only way to learn the state | Edits applied one by one, no pre-check | All-or-nothing: check every anchor, then write all or none | web W3 |
| F1.4 | data | Trailing space dropped from the replacement | `=MakeAction` after a replace_all ending in "=", `crafter )` after one ending in "(". Compiled, only clang-format noticed | Edit trims trailing whitespace from new_string | Warn when old or new starts or ends with whitespace. After replace_all show the changed token boundaries | G: A3, memory |
| F1.5 | data | Private-use glyphs invisible | "" in an anchor where the file holds U+E8F4. Glyphs lost on Write, empty glyphs committed | U+E000-F8FF print as nothing in Read, grep, sed and the agent's own text | Count PUA glyphs before and after each write. Flag "" in old_string where the file has a glyph. Prefer \uXXXX | svn-git ~12 |
| F2.1 | time | File changed between read and write | "File has been modified since read, either by the user or by a linter." ruff format, own scripts | Formatter, script, git checkout, the user, another agent, a rebase | Hash of the text last seen per file. Refuse a stale edit and show the current region. Re-read after any formatter, script or git command that touches the file | web W5 W10, D: 13, svn-git 3, G: A5 14 |
| F2.2 | noise | Write before read | "File has not been read yet. Read it first before writing to it." | First edit, or an edit after a compaction | Read automatically before the first edit | D: 23, G: A6 13 |
| F2.3 | data | Someone else edits the same tree | Another agent edited a file. The user's uncommitted GUI edits compiled into a test binary. Parallel subagents: "line numbers disagree between two of my own reads" | Shared working tree | Snapshot git status at start. Never stage, edit or revert files dirty before the session. Tell subagents which files the parent changes | D: memory, svn-git |
| F3.1 | data | Line endings change on write | Write turned CRLF into LF. sed -i: 365+/366- for one key. 389+/384- against 19 real lines. 336 CRLF lines spliced into an LF file reached SVN. One stray CRLF: all 624 lines rewritten. "LF will be replaced by CRLF" 30x D:, 81x svn-git | Endings are per file. Write writes LF. Edit keeps endings (one note disagrees). Python open(p,'w') without newline='' rewrites every ending. Git Bash sed -i strips CR | Record ending counts before (git ls-files --eol or bytes). Convert new text to that ending or refuse. After: fail if the dominant style changed or untouched lines differ. Compare git diff --numstat with and without --ignore-cr-at-eol | x-graph F1, web W8, D: 30, svn-git 81, G: A11 |
| F3.2 | time | Git Bash tools lie about CR | grep -c $'\r$' said every line is CRLF, or 0 then 760 for the same file | Git Bash tools normalise endings on read | Never infer endings from shell tools. Ask git or count bytes | x-graph F3, D: memory |
| F3.3 | data | Non-UTF-8 bytes replaced by U+FFFD | "Łukasz" became U+FFFD after an Edit. 334 text files not valid UTF-8. Read showed U+FFFD 391 times | cp1250 headers, decoded as UTF-8, written back as EF BF BD | Scan for invalid UTF-8 before an edit. Edit bytes or re-inject the original bytes outside the hunk. After: fail if EF BF BD grew or the diff touches lines not named | x-graph F2, D: 391 |
| F3.4 | data | BOM lost or added | utf-8-sig added a BOM. Heredoc and Python writes drop it | BOM is per file. PowerShell 5.1 -Encoding utf8 adds one | BOM state after equals before. Lint utf-8-sig writes | D: survey, svn-git 1 |
| F3.5 | data | PowerShell changes bytes on write, redirect and pipe | 5.1 writes UTF-16 by default, pwsh UTF-8. A > redirect re-encodes and turns LF into CRLF. git archive piped into tar corrupts | Two editions. Pipelines carry strings | Explicit -Encoding. Byte pipes and redirects through cmd /c | x-graph F5 R5, D: memory |
| F3.6 | data | File cut to 0 bytes | open(p,'w') truncated, then UnicodeEncodeError. The call still reported exit 0 | Truncate on open, before encoding. Default code page cp1250 | Fail when the size collapses. Write a temp file and rename | svn-git |
| F3.7 | data | Staged copies must keep index bytes | History rewrite needed the index's exact bytes | git hash-object without --no-filters can re-filter | Hash exactly what was extracted. Prove the final tree matches byte for byte | x-graph F4 |
| F3.8 | noise | Indent style does not match the file | Many files mix tab and 4-space line starts | Per-file style, the agent picks its own | Each added line uses its neighbours' indent character | D: survey |
| F3.9 | noise | Rewriters change more than asked | Set-Content appends a final newline. A re-emitting writer normalises whitespace | Whole-file rewrite instead of a hunk edit | The diff contains only the intended hunks | D: memory |
| F4.1 | data | Files changed by script instead of the edit tool | D: ~1,800 shell writes (inline Python 733, cat > heredoc 443, sed -i 228, Set-Content/Out-File 228, writeFileSync 119, perl -pi 53) against 8,269 Edit calls. svn-git ~570 and 81 p_*.py scripts in one session, Edit 13 errors in 762 | Auto mode tells the agent to prefer sed, heredocs and short scripts. Fallback after EPERM (his 10.1) | Block script writes to tracked files, allow the scratchpad. A script edit goes through the same gate and byte guard | web W9, D: ~1,800, svn-git ~570, G: 119 |
| F4.2 | data | Backslash escapes corrupted on the way to the file | '\\0' in a heredoc wrote a real NUL. D:<FF>ort for D:\fort, D:\dashboard<TAB>runk. A BEL in C#. "\n" became a real newline | The Bash tool halves \\ to \ even inside a quoted <<'EOF'. Non-raw Python strings then make real bytes | Reject heredocs and -c bodies with \. After a write fail on new NUL or C0 bytes, a TAB in a path token, a literal split across lines. "Binary file matches" is an alarm | D: memory, svn-git ~14, G: B2 |
| F4.3 | time | Long heredocs fail to parse | "unexpected EOF while looking for matching `''". 10 of 63 heredocs over 60 lines failed, 0 of ~353 shorter | Inferred transport or quoting limit. First failing line has an apostrophe | bash -n first. Reject heredocs over ~50 lines, route to Write | D: 36, svn-git 10, G: B3 63 |
| F4.4 | data | Backticks vanish from an inline script | Every `symbol` gone from a committed doc, no error | Backticks inside double quotes run as command substitution | Block backticks in double quotes | G: B4, memory 12 |
| F4.5 | time | Python string escaping errors | unterminated string literal (ROOT + '\' + rel). invalid escape sequence \s \S. 'unicodeescape' codec ... truncated \UXXXXXXXX | Windows paths and regexes in plain literals | py_compile the body first. Raw strings or forward slashes | svn-git 9, G: B2 B6 |
| F5.1 | time | Moved JSX kept its old indentation | 2 re-indent passes | Manual re-indent | Run the formatter on changed files, show the diff | web W6 |
| F5.2 | time | New sibling needed a wrapper | JSX single root | - | Parse after the edit | web W7 |
| F5.3 | time | Missing imports after adding code | Found by the linter later | - | Lint the changed file right after the edit | web W11 |
| F5.4 | time | Leftovers after removing code | Unused helpers, F841 | - | Lint right after | web W12 |
| F5.5 | time | Type annotation missing | mypy list[str] | - | mypy the changed module | web W13 |
| F6.1 | time | Guessed path does not exist | "File does not exist", "No such file or directory" | Guessed or moved layout, a type name taken as a file name, a glob with no match passed literally, an option after -- | Check each path and glob before the call. On a miss print the nearest path by basename from git ls-files | D: ~230, svn-git ~45, G: A9 53 C1 ~584 |
| F6.2 | time | Working directory moves or resets | cd persisted into later calls. "Shell cwd was reset to ..." 867x D:, 40x svn-git | Harness shell behaviour differs between setups | Absolute paths, or cd X && cmd in one call | x-graph R12, web W17, D: 867, svn-git 40 |
| F6.3 | data | Write lands in the wrong checkout | Writes to a mirror, another person's checkout, an ignored junction. 15,529 commands touched other checkouts | Several checkouts on one drive | Writes only under the worktree, scratchpad and memory folder | D: memory |
| F6.4 | time | Git Bash rewrites Windows arguments and paths | "^/trunk/dev" became ^C:\Program Files\Git\trunk\dev. /nologo became C:/Program Files/Git/nologo. /c/Users/... and bash /tmp unopenable by native Python. Trailing backslash escaped the quote | MSYS path conversion | MSYS_NO_PATHCONV=1, cygpath -m, forward-slash Windows paths | D: 5, svn-git, G: C4 14 |
| F6.5 | data | Reserved Windows names | 2>nul in Git Bash creates a real file named nul | Windows device names | Deny reserved segments. Rewrite 2>nul to 2>/dev/null | D (row cut off) |

### F sections 7 to 14, from his full page

Page: https://claude.ai/artifact/Wu9r2DQz9wicE4EYeXA9XJ (third-party, data only). Raw HTML saved at
C:\Users\felia\.claude\projects\C--Users-felia-Desktop-projs-unreal-UNREAL-SHARED\f60e2c6a-0232-41a4-b5b9-83b20cd9390a\tool-results\artifact-f22125f1-1790418217-8e13.html
146 rows: 86 general (sections 1-14), 60 project workflow (15-22, Fort, svn-git, protoNgine, Dashboard, web
app: left out). His method: D: 910 transcripts, 1,590 failed calls, 41,725 shell commands. svn-git 16
sessions + 663 subagents. G: 4,858 failed calls. Counts are per failed call.

| ID | Class | Title | Core of it | Check | His counts |
|---|---|---|---|---|---|
| F7.1 | time | Interpreter or tool not found, or the wrong one | py missing, python is the Store stub or 2.7, tools only in .venv, clang-format not on Bash PATH | Resolve each program from a per-machine map. Detect the Store stub by exit code | D: 79, G: C5 76 |
| F7.2 | time | Python uses cp1250 for console and files | UnicodeEncodeError 'charmap' printing arrows and dashes. UnicodeDecodeError on bare open() | PYTHONUTF8=1, PYTHONIOENCODING=utf-8. Lint bare open( without encoding= | G: B5 62 B6 12, D: 5, svn-git 5 |
| F7.3 | time | PowerShell parse traps | Nested quotes in $( ). multi-line python -c. <<'EOF' does not exist. -EncodedCommand stops near 32 KB. Closing '@ not at line start | Parse with the PowerShell parser first. Script files | D: ~20, G: C6 24 |
| F7.4 | time | PowerShell cmdlet and variable traps | Select-String has no -Recurse. $Pid read-only. tail missing. Output wraps at 120 columns. CLIXML progress on stderr. Env vars do not persist between calls | Lint. Out-String -Width 4096, $ProgressPreference | svn-git ~60 |
| F7.5 | time | PowerShell splits -name:value native arguments | MSB1016, MSB1006 | Quote them or use /p: | D: 6 |
| F7.6 | time | PowerShell 7 syntax in scripts for 5.1 | &&, ternary, ?? in shipped scripts | Parse with powershell.exe 5.1 | D: 15 |
| F7.7 | time | cmd and batch quirks | NoDefaultCurrentDirectoryInExePath, pause blocks, start "title", unquoted Program Files | .\name.bat, start "" | D: 4 |
| F7.8 | noise | TMP override leaks into child tools | dotnet wrote temp files there, folder undeletable | Do not override TMP | svn-git |
| F7.9 | time | A define lost its quotes | response-file parsing strips outer quotes | Unit-test the flag extractor | x-graph R6 |
| F7.10 | time | Text-matched the wrong XML block | awk took the first Release block | Parse XML with an XML parser | x-graph R7 |
| F8.1 | data | Pipe hides the real exit code | pytest | tail exit 0 over "No module named pytest". ctest | tail && git commit over a red suite. ~95 exit-0 results holding errors | pipefail, log then exit code then read. Refuse build or test piped to head/tail/grep | svn-git ~95, web W14 |
| F8.2 | data | Filter cuts important lines | Select-Object -First N kills the native command mid-build. 764 filtered builds, 150 errored | Full output to a log, then errors + last 20 + exit code | D: 764, svn-git 19 |
| F8.3 | noise | Exit code 1 that is not an error | grep no match 1, diff 1, ls missing 2 stop && chains | Label known exit codes | D: ~200, svn-git 73, G: ~415 |
| F8.4 | time | Tool output in the system language | English-only filters matched nothing | DOTNET_CLI_UI_LANGUAGE=en, VSLANG=1033, match codes not words | D: 204, svn-git 449 |
| F8.5 | noise | Mojibake in output | U+FFFD in 426 Bash outputs | UTF-8 console or cp fallback. Never copy mojibake back into a file | D: 426 |
| F8.6 | time | Summary line missing from test output | tail -1 showed dots | Machine-readable report | web W18 |
| F8.7 | noise | Log searches raise false alarms | a summary line containing the word it reports, 219 of 310 alarms false | Anchor at line start | G: D4 219 |
| F8.8 | time | Wrong guess about output structure | KeyError parsing a JSON output | Print keys first | G: C9 32 |
| F8.9 | noise | Locale number and name formats | comma decimals, localised group names | InvariantCulture, SIDs | D: memory |
| F9.1 | time | sleep chains blocked | "Blocked: sleep 60 followed by ..." | Monitor or run_in_background | D: 30, G: E2 26 |
| F9.2 | data | Background output read before the run ended | "no result yet" read as finished | Track the process, not the file | svn-git |
| F9.3 | time | Broad searches time out or hit locked files | grep -r over data folders past 120 s | Default excludes, point to the Grep tool | D: 9, svn-git 153 |
| F9.4 | time | Commands hit the ten-minute cap | Exit code 143 timed out after 10m | Detach, poll a log, timeout every wait | G: C10 |
| F9.5 | time | Silent long run looked hung | 10 minutes of nothing | Progress lines and ETA | x-graph R9 |
| F9.6 | data | Script edited while a run used it | PowerShell re-reads .ps1 per invocation | Snapshot scripts into the run's folder | x-graph R8 |
| F10.1 | time | Edit fails, file is locked | "EPERM: operation not permitted, rename ..." | Edit writes a temp and renames. Detect the holder, retry with backoff, never fall back to a script | D: 34, G: A4 6 |
| F10.2 | time | Build output locked by a running program | MSB3027, MSB3026, lld-link failed to write | List holders under the output folder. One build per checkout | D: 29, svn-git 26, G: 28 |
| F10.3 | data | Killing by name hits the user's programs | 168 by-name kills | Stop only pids the session started | svn-git 168 |
| F11.1 | time | Remove-Item guard blocks the command | "Remove-Item on system path '/c' is blocked" read from -replace '\\','/' | Remove-Item alone with one literal path | D: 18, svn-git 12, G: 38 |
| F11.2 | time | Auto-mode classifier refuses or is down | git checkout --, reset --hard, sed -i on ~/.claude; 22 outages | Route destructive verbs to the user | D: 27, G: 35 |
| F11.3 | time | Actions the user stops | kills, long builds, python -c source patches | Ask first | D: 25 |
| F12.1 | data | Result comes from an old binary | a failed compile leaves the previous exe, a filter matching nothing prints SUCCESS | Gate on build exit, exe timestamp, case count | several |
| F12.2-12.8 | mixed | Test helpers (fixtures, locators, waits, media emulation, screenshots, dates, pinned timing) | not file IO | - | web, svn-git, x-graph |
| F13.1 | data | Scratch files inside the repo | helper scripts and __pycache__ in the tree | Refuse new untracked scripts in the worktree | x-graph, web, D: |
| F13.2 | time | A command created files | uv run created uv.lock | Diff untracked files before and after | web W16 |
| F13.3 | data | Broad staging | git add -A by folder | List new untracked files first | web W29 |
| F13.4 | time | No way to stage by hunk | git add -p is interactive | Ship a hunk splitter (git apply --cached --recount) | web, svn-git |
| F13.5 | data | Shared stash across worktrees | another session can pop your stash | stash push -u -m tag, apply by SHA | x-graph G2 |
| F13.6 | data | Undo with git checkout -- file lost edits | whole-file undo threw away other edits | Copy to scratchpad first, undo one hunk | svn-git |
| F13.7 | noise | git status lists unchanged files | stat cache | git diff --name-only | svn-git |
| F13.8 | time | Commit rules | format, no Co-Authored-By | commit-msg hook | D: |
| F13.9 | data | Junk in the staged diff | U+FFFD, ending churn, scratch files, .rej | pre-commit byte guard | D: |
| F14.1 | time | Tool input not valid JSON | "Read was called with input not parsed as JSON", doubled comma, unescaped backslash, control char | Validate and repair arguments | D: ~25, G: 45 |
| F14.2 | time | MCP call shape errors | body over 20,000 chars, missing fields | Check shape and length first | G: 148 |
| F14.3 | noise | File too big for one Read | "File content (25791 tokens) exceeds maximum (25000)" | Size first, offset/limit | D: 2, G: 8 |
| F14.4 | time | Read refuses a text .dat as binary | extension-based binary check | Sniff bytes | D: 4 |
| F14.5 | time | Grep pattern rejected | look-around not supported | Lint, PCRE2 | D: 9, G: 6 |
| F14.6 | noise | Edit with identical strings | "No changes to make" | Treat as a freshness signal | D: 4 |

His build order (core): 1 freshness gate + anchor helper, 2 byte guard around every write, 3 shell-write
policy + inline-script lint, 4 exit status + result interpreter, 5 path resolver + cwd pin, 6 environment
defaults, 7 lock + process preflight, 8 command policy, 9 verify each changed file, 10 commit hygiene,
11 test helpers, 12 tool-call input checks. First scope: 1-4. Hook map: SessionStart (env facts, git status
and process snapshot), PreToolUse Edit|Write (gate, write roots, reserved names, locks, byte snapshot),
PostToolUse Edit|Write (byte guard, per-language verify), PreToolUse Bash|PowerShell (shell-write policy,
lint, paths, env), PostToolUse Bash|PowerShell (result interpreter, byte guard on touched files, mark
"re-read needed"), build wrappers, git hooks. Inferred only, not observed: why long heredocs fail.

## Part N: our four projects (CLICKER, OrbitalDrift, SmartTablesHost, UNREAL-SHARED)

Filled from the scratchpad decomposition and tx_events.jsonl. Each entry: symptom, cause, evidence with
counts, the tool's check, and which F entry it confirms or extends.

The merged catalog (98 findings, F ids kept) is published: https://claude.ai/artifact/NDhF5JoHcXy6mDDPSecZLu,
source io_traps.html in this scratchpad. Analysis scripts: tx_scan.py (writes tx_events.jsonl), tx_report.py,
tx_eof.py, repo_bytes.py, eol_probe.py.

- N-backslash: verified live 2026-09-27. Bash tool: echo 'a\\b' prints a\b, 'a\\\\b' prints a\\b, inside
  single quotes and inside a quoted <<'PY' heredoc (Python saw r"\\n" as 2 characters). PowerShell tool:
  'a\\b'.Length is 4, unchanged. Confirms F4.2 and names the layer: the Bash tool, before bash parses.
- N-transport-scope (2026-09-27, live): the Write tool kept `\\` and `\\\\` byte-exact in a 125 KB page. The
  PowerShell tool took a 9 KB here-string intact (8,971 chars, both backslashes kept). The 7.8 KB cut and the
  backslash halving are the Bash tool's alone, so content passed as a structured tool argument is safe.
- N-shell-usage: 97,579 Bash and 5,565 PowerShell calls. 54% of Bash calls run python, 16.5% only inspect
  (grep 72k, head 45k, tail 24k, sed -n 23k segments), 13.5% mutate, 7.3% wait or manage processes
  (sleep 8,951), 5.5% git, 3.6% build or editor runs. A Bash replacement must cover python first.
- N-regex-silent-zero: a regex written in a heredoc lost a backslash and matched nothing, with no error.
  A count of 0 looked like a real result. Extends F4.2: the corruption also hits read-only analysis.
