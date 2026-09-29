---
name: io-guard
description: What an io-guard code means and the call that fixes it, and which io tool does which file or shell job. Read it when a tool result names an io-guard code such as SHELL_WRITE, ANCHOR_AMBIGUOUS or FILE_LOCKED, when a note says io-guard fixed a call, or before several edits to one file, a splice between markers, a log append, a long run, or formatting changed lines.
---

# io-guard

io-guard checks each file and shell call before it runs and after. It fixes what it can fix without changing
what the call means, and a note says so. It refuses the rest with a code, what happened, and the call to make
instead.

| Rule | Why |
|---|---|
| **After a refusal, make the call its fix names, once, as written.** | io-guard builds the fix from the file or the command itself. |
| **Never route around a refusal through the shell or a script.** | A shell write skips every check, and SHELL_WRITE refuses it too. |
| **Load an io tool with ToolSearch before its first call**, with the query `select:` and the name the table gives. | The io tools stay behind tool search until loaded. |
| **After an io tool changes a file, Read the file before the next Edit of it.** | Claude Code tracks only its own tools' writes. |
| **Wait for a long run with `io.run` in the background and `io.status`**, never with a chain of sleep commands. | Claude Code blocks sleep chains. |
| **A note that io-guard fixed a call asks for nothing.** | The call ran as the note says. |

## Pick the tool

Edit makes one change in a file, and Write makes a new file or replaces one whole. io-guard fits both to the
file's line endings, BOM and indent before they run. The io tools do what the built-in tools do badly or not
at all:

<!-- Generated from the io server's tool list. An edit between here and the end line is overwritten. -->
| Job | Tool | Call it as |
|---|---|---|
| Read a file byte for byte | `io.read` | `mcp__plugin_io-guard_io__io_read` |
| Edit a file in several places at once | `io.edit` | `mcp__plugin_io-guard_io__io_edit` |
| Replace the text between two markers | `io.splice` | `mcp__plugin_io-guard_io__io_splice` |
| Append lines to a file | `io.append` | `mcp__plugin_io-guard_io__io_append` |
| Run a program without a shell | `io.run` | `mcp__plugin_io-guard_io__io_run` |
| Check a background run | `io.status` | `mcp__plugin_io-guard_io__io_status` |
| Read the new lines of a log | `io.read_log` | `mcp__plugin_io-guard_io__io_read_log` |
| Format the changed lines of files | `io.format` | `mcp__plugin_io-guard_io__io_format` |
| Keep files before a task | `io.snapshot` | `mcp__plugin_io-guard_io__io_snapshot` |
| Put files back as a snapshot kept them | `io.restore` | `mcp__plugin_io-guard_io__io_restore` |
| Show whether a pass changed code | `io.compare` | `mcp__plugin_io-guard_io__io_compare` |
| Stage chosen hunks of a file | `io.stage` | `mcp__plugin_io-guard_io__io_stage` |
| Open io-guard's settings page | `io.dashboard` | `mcp__plugin_io-guard_io__io_dashboard` |
| Read or change one io-guard setting | `io.config` | `mcp__plugin_io-guard_io__io_config` |
| Ask the user to approve a project's commands | `io.trust` | `mcp__plugin_io-guard_io__io_trust` |
<!-- The generated tools table ends here. -->

## What io-guard fixes on its own

- **Write:** the file's line endings, BOM and last line break (`EOL_CONVERTED`, `BOM_RESTORED`).
- **Edit:** a new_string indented with tabs beside lines indented with spaces, or the other way round, takes
  their indent (`INDENT_MISMATCH`).
- **After a write:** a BOM or line endings the write lost go back on, and a note says to Read the file again.
- **Bash:** a long heredoc or `python -c` body moves into a file the command then reads (`BODY_MOVED_TO_FILE`).
  An argument Git Bash would turn into a path stays as written (`MSYS_PATH`), and a Windows path whose last
  backslash would escape its closing quote gets forward slashes (`TRAILING_BACKSLASH_QUOTE`).

A fixed Bash command goes through the user's rewrite mode for the session's permission mode. In `refuse`, the
default in auto and dontAsk, the call is refused and the reason carries the fixed command, so run that command
as given. In `ask`, the default in default, acceptEdits and plan, the user sees the fixed command and approves
it. In `allow`, the default in bypassPermissions, it runs at once.

## Wait for a long run

1. Call `io.run` with `background` true. It answers at once with a handle and the run's `log_path`.
2. Do other work, then call `io.status` with the handle. It answers `running`, or `ended` with the exit code,
   the error lines and the last lines of the log.
3. Call `io.read_log` with the `log_path` for the lines the log gained since the last call.

A run to its end waits up to `timeout_s`, 120 seconds unless the call or the config says otherwise, and
io-guard stops it past that.

## The codes

A refused call did not run. A warning, or a note that io-guard fixed something, came with a call that ran.

<!-- Generated from io-guard's code list. An edit between here and the end line is overwritten. -->
| Code | What happened | What to do |
|---|---|---|
| `ANCHOR_AMBIGUOUS` | The Edit's old_string is in the file more than once, so the Edit was refused. | Call Edit again with a longer old_string that names one place, or with replace_all set. |
| `ANCHOR_NOT_FOUND` | The Edit's old_string is not in the file, so the Edit was refused. | Call Edit again with old_string copied from the lines the message shows. |
| `BACKSLASH_TRANSPORT` | The Bash tool on Windows halves a pair of backslashes in this command. | If the command needs both, put the text in a file with the Write tool and read it from there. |
| `BACKTICK_IN_DOUBLE_QUOTES` | Bash runs the text between backticks inside double quotes as a command. | Put that text in single quotes, or escape each backtick with a backslash. |
| `BODY_MOVED_TO_FILE` | The command's body was written to a file, and the command reads that file. | Nothing to do. |
| `BOM_CHANGED` | The write added or removed the file's byte order mark. | Write the file again with its BOM as it was. |
| `BOM_RESTORED` | io-guard kept the file's byte order mark, which the Write tool drops. | Nothing to do. |
| `BUDGET_EXCEEDED` | io-guard ran out of time on this call and skipped its remaining checks. | Nothing to do, because the call went ahead without those checks. |
| `CANCELLED` | The client cancelled the io tool call before it finished. | Call the tool again if its result is still needed. |
| `COMMIT_POLICY` | The commit message holds text the user's commit policy forbids, so the commit did not run. | Take that text out of the message, then commit again. |
| `CONFIG_REFUSED` | The setting was not written: the key is unknown, the value does not fit it, or this file may not set it. | Use a key and a value the message names. |
| `CONTROL_BYTES_ADDED` | The write added NUL or other control bytes to a text file. | Remove them with the Edit tool, on the lines the message names. |
| `DIALECT_MISMATCH` | The command is written for the other shell. | Send it to the tool for that shell, or write it for this one. |
| `ENCODING_INVALID` | The write left bytes that are not UTF-8, or U+FFFD characters where others could not be read. | Read the lines the message names, and put back the characters they lost. |
| `EOL_CONVERTED` | io-guard wrote the new text in the file's own line endings. | Nothing to do. |
| `EOL_MISMATCH` | The new text's line endings differ from the file's. | Write the whole file in one ending. |
| `ERRORS_IN_OUTPUT` | The output has lines that report errors. | Fix the first one, then run the command again. |
| `EXIT_BENIGN` | The exit code is an answer the program gives, such as grep's 1 for no match, not a failure. | Put \|\| true after that program when its answer is expected. |
| `FILE_LOCKED` | Another process holds the file open, so the tool could not replace it. | Close that program or wait for it, then call the same tool again, never a shell write. |
| `FORMAT_FAILED` | The format command could not start, failed, or gave no text back, so io.format wrote nothing. | Fix what the message names, such as a line of the project's formatter config, then call io.format again. |
| `GUARD_ERROR` | An io-guard check failed on this call, so io-guard skipped that check and let the call go on. | Nothing to do, because the debug log holds the details. |
| `HANDLE_EXPIRED` | The handle names work io-guard no longer holds, because it ended over an hour ago or the server restarted. | Start the work again with the tool that made the handle. |
| `HUNK_NOT_FOUND` | No unstaged hunk of the file meets the lines or the task asked for, so io.stage staged nothing. | Call io.stage with lines from the hunks the message lists, or with the task's tag. |
| `INDENT_MISMATCH` | The new text's indent differs from the lines around it, tabs against spaces. | Indent the new text as the lines around it are. |
| `INLINE_SCRIPT_INVALID` | The Python program in this command does not compile. | Fix the line the message names, then run the command again. |
| `INVISIBLE_ADDED` | The write added a character the Read tool shows as nothing, such as U+FEFF or a zero-width space. | If the file should hold an escape rather than the character, write the escape again with its backslash doubled in the tool call. |
| `LINES_JOINED` | The Edit deletes old_string and the line break after it, so the lines around it would join. | Move old_string one line break later, so it ends with the line break instead of opening with it. |
| `LINKED_PATH` | The path runs through a junction or symbolic link into another repository. | Change the file in the repository that owns it, unless the task is about that repository. |
| `MOJIBAKE` | The output holds text that went through the wrong code page. | Copy none of that text into a file, and run the command again with UTF-8 input and output. |
| `MSYS_PATH` | Git Bash would turn an argument that starts with a slash into a path under its install folder, so io-guard kept it as written. | Nothing to do. |
| `NON_ASCII_ADDED` | The write added non-ASCII characters to a file this project keeps ASCII. | Replace them with ASCII, on the lines the message names. |
| `NOT_PORTABLE` | The command uses bash 4 syntax or a GNU option, which this machine's bash 3.2 or BSD tools read another way or lack. | Write it as the message says, for bash 3.2 and the BSD tools. |
| `OUTPUT_SAVED` | The output was too long to show, so io-guard shows its first and last lines and its errors. | Read the saved file with offset and limit for the rest. |
| `PATH_NOT_FOUND` | The path does not exist. | Call the tool again with one of the paths the message names. |
| `PATTERN_INVALID` | ripgrep rejected the Grep pattern before it searched. | Call Grep again with the pattern the message gives. |
| `PIPE_HIDES_EXIT` | A pipe gives the command the exit code of its last part, which hides a build or test failure. | Read the output for the result, not the exit code. |
| `POWERSHELL_TRAP` | PowerShell refuses this command before it does anything. | Change the command as the message says, then run it again. |
| `PROJECT_COMMANDS_UNTRUSTED` | The project's .claude/io-guard.json names commands io-guard starts, which the user has not approved, so io-guard ran only the user's own. | Call io.trust, so the user can approve them in the permission prompt. |
| `READ_ONLY` | The file is read-only, so the write would fail or stop the session at a prompt. | Ask the user to make it writable, such as by checking it out in their version control. |
| `READ_TOO_LARGE` | The file is larger than one Read returns. | Read it in the parts the message names, with offset and limit. |
| `RESERVED_NAME` | The path is a Windows device name, such as nul or con, which Windows tools cannot open or delete as a file. | Use /dev/null in Bash, or another name for a file. |
| `RESTORE_ASKED` | The restore would replace files that changed since the snapshot, so the user decides whether io.restore runs. | Wait for the user's answer, and write nothing to those files meanwhile. |
| `REWRITE_CONFLICT` | Two io-guard fixes changed the same part of this call, so io-guard kept the first and dropped the second. | Nothing to do, because the first fix applied. |
| `RULE_ASKED` | One of the user's permission rules asks about this command, so the user decides whether io.run runs it. | Wait for the user's answer, and run nothing else in its place. |
| `RULE_DENIED` | One of the user's permission rules denies this command, so io.run did not run it. | Leave the command out, or ask the user whether the rule should change. |
| `SEARCH_TOO_BROAD` | The search ran out of time before it finished. | Search a narrower folder, or add a glob or type filter. |
| `SERVER_DOWN` | io-guard's io server stopped, so tool calls ran without its checks. | Claude Code starts it again at the next tool call, and /mcp shows why when it cannot. |
| `SHELL_WRITE` | The command writes a file git tracks through the shell, around io-guard's checks. | Use the Edit tool to change the file, or the Write tool to replace it whole. |
| `SIZE_COLLAPSED` | The file holds far fewer bytes than the call should have left in it. | Read the file, and write the missing text back. |
| `SNAPSHOT_TOO_LARGE` | The paths hold more files or bytes than one snapshot keeps, so io.snapshot kept nothing. | Call io.snapshot on fewer paths, such as only the folders the task changes. |
| `SPACE_DROPPED` | old_string ends in a space or tab that new_string lacks, so the Edit would join new_string to the text after it. | End old_string and new_string one character later, with the space inside both. |
| `STAGE_FAILED` | git could not stage the hunks, so the index is as it was. | Fix what git's message names, such as a file git does not track yet, then call io.stage again. |
| `STALE_BINARY` | The last build in this session failed, so this run used what an earlier build made. | Fix the build and build again before trusting this result. |
| `STALE_VIEW` | The file holds something other than what the call expected. | Read the file again, then change only what differs. |
| `STOPS_BY_MATCH` | The command stops every process a name or a match picks, other sessions' processes too. | Stop the one process by its id. |
| `TOUCHED_BY_SHELL` | A shell command changed files the agent had read, or made new ones. | Read the changed files again before the next Edit. |
| `TRAILING_BACKSLASH_QUOTE` | A backslash before a closing double quote escapes the quote in bash, so io-guard wrote the path with forward slashes. | Nothing to do. |
| `TRANSPORT_BUDGET` | The command is longer than the Bash tool carries on this platform. | Write the script to a file with the Write tool, then run the file. |
| `TRUST_ASKED` | The project's .claude/io-guard.json names commands io-guard would start, so the user decides whether they may run. | Wait for the user's answer. |
| `UNINTENDED_CHANGE` | Lines changed that the call did not ask to change. | Read the lines the message names, and put back any change the call did not make. |
| `VERIFY_OUTPUT` | The verify command for this file printed something, failed, ran out of time or could not start after the write. | Read what it printed, and fix what it names before the next step. |
<!-- The generated codes table ends here. -->
