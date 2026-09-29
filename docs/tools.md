# io-guard's tools

A few jobs have no safe built-in tool, so io-guard adds its own. The agent calls them like any other tool. The
[README](../README.md) says what io-guard does, and [the settings page](settings.md) lists each tool's settings.

| Tool | What it does |
|---|---|
| `io.read` | Shows a file's lines exactly as the file holds them, with its line endings, BOM, encoding and indent |
| `io.edit` | Makes several edits in one file, all or nothing, in the file's own endings, BOM and encoding |
| `io.splice` | Replaces the text between a start marker and the end marker after it |
| `io.append` | Adds lines to the end of a file, dated if you ask, wrapped at the file's `.editorconfig` column |
| `io.run` | Runs a program from a list of arguments, or a script byte for byte, with no shell in between, under your Bash and PowerShell rules |
| `io.status` | Says whether a background `io.run` still runs, and how it ended |
| `io.read_log` | Reads the lines a log gained since the last read, less your noise patterns |
| `io.format` | Runs your formatter, clang-format by default, on the lines changed since the last commit and no others |
| `io.snapshot` | Keeps a copy of files, folders or globs under a name for seven days, before a pass over many files |
| `io.restore` | Puts back the files a snapshot kept, only those that changed, after your yes |
| `io.compare` | Shows whether a pass changed code since a snapshot, ignoring comments or include lines, and where |
| `io.stage` | Stages the parts of a file that hold the lines you name, or that one task wrote, and never commits |
| `io.config` | Reads one io-guard setting, or writes it into your config or the project's |
| `io.dashboard` | Opens io-guard's settings page, on this machine only |
| `io.trust` | Lets io-guard run the `verify` and `format` commands a project names, after your yes |

## Editing files

`io.edit`, `io.splice` and `io.append` write a file once, only when every place they name matched once. A
failed one writes nothing and names the lines it nearly matched. Two subagents editing one file take turns.
After one of them changes a file, the built-in Edit tool needs a fresh Read of it, and every result says so.

## Formatting

`io.format` hands the formatter only the lines `git diff` says changed, or the whole file when git has no
commit of it, or the lines the call names. The file keeps its line endings and BOM whatever the formatter's
config says, and a change the formatter makes away from those lines, such as a `// namespace` closer at the
end of the file, stays out. When the formatter fails on one file, no file is written. With `dry_run` set, it
writes nothing and returns each file's diff, so you see what the formatter would change first, and `lines`
takes each file's own lines in one call.

## Running programs

`io.run` meets your deny and ask rules for Bash and PowerShell, from every settings file Claude Code reads. A
deny rule refuses the run, and an ask rule brings up Claude Code's own permission prompt. That holds for a
command inside `bash -c` or `pwsh -Command` too. A script body or a `python -c` string that mentions a rule's
program, such as `git` for `Bash(git push *)`, also brings up the prompt, since no rule can see what code does
with it. A background run's handle lasts an hour past the program's end.

## Undoing a task

`io.snapshot` keeps its copies in io-guard's folder, up to 5,000 files and 512 MB each, and deletes them after
seven days. A glob keeps every file it matches, and a name that exists as written, such as `[id].tsx`, is
that file. `io.restore` undoes a task file by file, where `git checkout` would throw away every other edit
of the file too. It writes back only the files that changed since the snapshot, into their folders even when
a folder was deleted, and Claude Code's own permission prompt asks you first, naming the files whose edits
you'd lose.

## Splitting work into commits

`io.stage` splits a session's work into commits without `git add -p`. Give it lines, or the name you gave
`io.snapshot` before a task, and it stages the parts the journal says that task wrote. A part holding two
tasks' lines is left for you, and named.
