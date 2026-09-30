---
title: A new file in a new folder takes LF where every file around it is CRLF
stage: I
area: bytes
created: 2026-09-30
status: done
depends-on: []
findings: [BYT-1]
platforms: [windows, macos]
commit: "fix: a new file in a new folder takes the nearest files' ending"
---

## Why

Raised from SmartTablesHost on 2026-09-30, in a live session. Six new C++ files went through Claude Code's
Write tool in one task, with io-guard's hooks on.

Three went into folders that already held files, and io-guard wrote them CRLF with this note:

```
EOL_CONVERTED: io-guard wrote the content with CRLF line endings, and a final newline, as a new .cpp here takes them.
```

```
Source/SmartTablesHostDev/Dev/Commands/StReelCommands.h     crlf 14   bare lf 0
Source/SmartTablesHostDev/Dev/Commands/StReelCommands.cpp   crlf 75   bare lf 0
Source/SmartTablesHostDev/Tests/StReelTests.cpp             crlf 48   bare lf 0
```

Three went into two folders the same calls created, `Source/SmartTablesHost/Public/` and
`Source/SmartTablesHost/Private/`. They came out LF, and no note came with them:

```
Source/SmartTablesHost/Public/StReelServerViewModel.h       crlf 0    bare lf 32
Source/SmartTablesHost/Public/StReelListViewModel.h         crlf 0    bare lf 45
Source/SmartTablesHost/Private/StReelListViewModel.cpp      crlf 0    bare lf 55
```

The folder one level up, `Source/SmartTablesHost/`, holds `SmartTablesHost.cpp`, `SmartTablesHostPrivatePCH.h`
and `SmartTablesHost.Build.cs`, all CRLF, and so does every other source file in the repository. The
repository's `.clang-format` says `LineEnding: DeriveLF`, and `core.autocrlf` is `true`.

**Once written, the LF sticks.** A later Write or Edit keeps the file's own ending, which is right for a file
somebody made that way on purpose and wrong for one io-guard made. The only way back is to delete the file and
write it again, and that lands in the same empty folder with the same result.

## What done looks like

- A new file in a folder with no files of its kind takes the ending of the nearest folder above that has some,
  or of the repository's files of that extension. The three files above come out CRLF.
- The write says which ending it chose and why, as the note above does for a folder with files.
- A test writes a `.h` into a new folder under a folder of CRLF `.h` files and reads back CRLF.

## What changed

Numbered 148 when it was picked up on 2026-09-30.

The report held, and the cause is in `checks/conform_write.py`. `new_file_target` took a new file's siblings
from `path.parent` alone. A folder the same Write creates holds no files, so with no `.editorconfig` and no
`eol` attribute it returned `None`, and the content stayed as the model wrote it, LF, with no note.
SmartTablesHost has no `.editorconfig`, and `git check-attr eol` on `Source/SmartTablesHost/Public/X.h` says
`unspecified`, so that was its path. The `.clang-format` and `core.autocrlf` the report names play no part:
io-guard reads neither for a new file's ending.

- `like_files` looks in the file's own folder first, then in each folder above it up to the repository's root,
  and takes the files with its extension from the first folder that holds any. `git.root` fails in a folder
  that does not exist yet, so the root is asked of the nearest folder that does. Outside a repository only the
  file's own folder is read, as before, so no file of another project sets the ending.
- The note names the folder when it is not the file's own: `io-guard wrote the content with CRLF line endings,
  and a final newline, as the .h files in Source/Game have them.`
- `.editorconfig` and `.gitattributes` still outrank the files, as `target_profile` orders them.

Not built: the report's fallback to "the repository's files of that extension". The walk up reaches the root
folder, and a repository with no file of that extension on the way has no convention of its own to copy.

The tests, in `tests/checks/test_conform_write.py`:

- `test_a_new_folder_takes_the_files_of_the_nearest_folder_above` writes `Source/Game/Public/New.h` beside
  CRLF `.h` files in `Source/Game`. It failed first with `('x\ny\n', [])`, the report's LF and no note, then
  passed with CRLF and the note.
- `test_a_new_folder_in_a_real_repository_takes_crlf` does the same in a real git repository through
  `Context.live`. Run against HEAD's `conform_write.py`, it failed with `'int b;\n'`.
- `test_the_walk_up_stops_at_the_repository_root` puts a CRLF `.h` above the repository. It passes before and
  after, and it holds the walk inside the repository.

The live probe: `live-new-folder` in `tools/probes/run_probe.py`, a git repository with a CRLF `Source/Game/a.h`,
where Haiku writes `Source/Game/Public/New.h` with the Write tool. Its first run failed with LF. The cause was
not the fix: the probe's work folder sits under this repository's `workbench/`, and this repository's own
`.editorconfig` says `end_of_line = lf`, which outranks the files. The same leak as task 146's `io-guard.json`.
The probe now gives its folder an `.editorconfig` of `root = true`, and the rerun passed, the file landing as
`int b;\r\nint c;\r\n`.

Evidence:

- `python tests/run_all.py`: 1,110 tests, OK, 2 skipped, against 1,107 at task 141.
- `live-new-folder`, `live-conform`, `live-verify` and `live-empty` passed on the CLI 2.1.283.

Docs: `docs/design/architecture.md`, beside `target_profile`, says where `conform.write` takes the siblings
from. The module docstring says the same.

Checked on Windows 10 on 2026-09-30. macOS is covered by CI only.
