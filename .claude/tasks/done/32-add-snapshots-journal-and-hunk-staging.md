---
title: Add snapshots, an edit journal and hunk staging
stage: H
area: mcp
created: 2026-09-27
status: done
claimed-by: Pala Elektroniczna, 2026-09-28
depends-on: [18, 23, 31]
findings: [GIT-4, GIT-6, VFY-6, BYT-9, BYT-10]
platforms: [windows, macos]
commit: "feat: snapshot files before a task, journal every write, and stage by hunk"
---

## Why

Three workarounds show what is missing:

- **No undo for a batch.** Agents copied files into before-folders first: 722 files in one, and 105, 79 and 37 in
  others.
- **No proof of a comment-only pass.** Agents wrote comment-stripping checkers to show that a pass changed no code.
- **No record of which edit belongs to which task.** To split one session's work into commits, SmartTablesHost
  replayed its own transcript with five scripts.

It comes after the measurement (D20), so task 31's numbers can reshape it.

## What to build

- **Journal.** The hooks record every write through Edit, Write or an io tool in io-guard's folder: the file,
  the hunk ranges, the tool, the time, and an optional task tag.
- **`io.snapshot(paths[], tag)` and `io.restore(tag, paths?)`.** The before-copies live in io-guard's folder,
  under a handle that expires after seven days (`docs/design/architecture.md`, section 7). A restore over newer
  edits elicits the user's yes first.
- **`io.compare(tag, mode)`.** Shows whether the code is unchanged, ignoring comments or ignoring include lines
  (VFY-6).
- **`io.stage(file, hunks[])`.** Stages the chosen hunks through `git apply --cached --recount` and keeps the index
  bytes exact (BYT-10). It never commits.

## Where

`plugins/io-guard/scripts/ioguard/mcp/tools_history.py`, `tests/mcp/test_tools_history.py`.

## Done when

- A batch across 10 files restores exactly: every file's hash matches its before-copy.
- Staging 2 of 3 hunks leaves the third unstaged, and `git diff --cached` shows exactly those 2.

## What changed

Four commits, one per part, each with its tests and docs. Both done-when checks hold: ten files of every kind
restore to their before-copies' hashes, and staging 2 of 3 hunks leaves the third unstaged with
`git diff --cached` showing exactly those 2.

- **Part 1, snapshot and restore, 2026-09-28.** `lib.snapshots` keeps a snapshot as
  `snapshots/<id>/snapshot.json` in io-guard's folder, beside a blob per file, found by its id or by the newest
  tag in the project, and deleted after seven days. `io.snapshot` takes files, folders and globs, up to
  `io.snapshot.max_files` of 5,000 and `io.snapshot.max_bytes` of 512 MB, past which it answers
  `SNAPSHOT_TOO_LARGE`. The new check `restore.ask` answers the PreToolUse hook on `io.restore` with `ask` and
  `RESTORE_ASKED` when the restore would replace changed files, and `io.restore` writes only a restore the hook
  recorded, once. Elicitation stays out, since no surface shows its form. `FsPort` gained `files_under`, and
  `lib.context.read_or_none` replaced three copies of the same read. `live-restore` passed on 2.1.281 and
  2.1.283. Tests: 746 before, 767 after.
- **Part 2, the journal, 2026-09-28.** `lib.journal` keeps `journal/<YYYY-MM>/<session>.jsonl` in io-guard's
  folder: per write the file, the lines, the tool, the time, the session's tag, and a 12-digit SHA-1 key per
  added and removed line, never text. The new check `journal.write` records Edit and Write at PostToolUse
  from verify.write's snapshot, which it reads with `SessionState.peek_snapshot` before verify.write takes it,
  and `mcp.in_place.write` records the io tools' own writes. `io.snapshot` sets the session's tag. Live on
  2.1.283, `live-restore` journaled its `io.edit` under the tag `probe`, and `live-verify` its Write and Edit.
  Tests: 767 before, 782 after.
- **Part 3, compare, 2026-09-28.** `lib.code_tokens` reads a C-family, Python or hash-comment file as its
  tokens less comments and layout, Python through its own tokenizer with docstrings dropped and indentation
  kept, or as its lines with the include lines apart. `io.compare(tag, mode, paths)` compares each file the
  snapshot holds in `code`, `includes` or `exact` mode, and names the first line that differs on each side.
  It uses no harness feature the other io tools do not, so it has no probe of its own. Tests: 782 before,
  797 after.
- **Part 4, staging, 2026-09-28.** `lib.hunks` reads one file's `git diff -U0` into hunks and writes a patch
  of the chosen ones byte for byte. `io.stage(path, lines | tag)` stages the hunks that meet the lines, or the
  hunks whose lines that say anything the journal gives the task, through the new `GitPort.stage_patch`, `git
  apply --cached --unidiff-zero --recount`, and never commits. A hunk mixing the task's lines with another's
  is left and named. New codes `HUNK_NOT_FOUND` and `STAGE_FAILED`. In a real repository, 2 of 3 hunks
  staged and the third stayed, every hunk of a CRLF `-text` file staged to the blob `git hash-object
  --no-filters` gives (BYT-10), and a tag staged its own `io.edit` and left another task's. `live-stage`
  passed on 2.1.281 and 2.1.283. Tests: 797 before, 810 after.
- **Docs.** `README.md` (the four tools, the folder's snapshots and journal), `docs/design/architecture.md`
  (layout, `GitPort`, codes, config keys, the section on keeping and putting back files, the journal,
  handles), `docs/architecture.svg` (the io tools box, the folder box), `docs/compat.md`,
  `docs/live-checks.md`, `CLAUDE.md` (the checks and tools), `context.md`, and the skill's generated tables.
- **Not built.** `io.restore` writes are not journaled, since a restore undoes. Elicitation stays out, since
  no surface shows its form, and the permission prompt carries the restore's question instead.
