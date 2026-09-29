---
title: Keep a file's mode and its symlink when io-guard writes it
stage: I
area: lib
created: 2026-09-29
status: open
depends-on: []
findings: [BYT-9]
platforms: [windows, macos]
commit: "fix: io-guard's writes keep a file's mode and its symlink"
---

## Why

The code review of 2026-09-29, slice C item 6. `lib/bytesio.py` `write_atomic` writes a `mkstemp` file and
renames it over the target. `mkstemp` creates the file at mode 0600 on macOS, and `os.replace` keeps the new
file's mode, so every io-guard write leaves the file 0600: an edited script loses its executable bit, and a
shared file loses its group and other read bits. A symlink target is replaced by a plain file, so a dotfile
linked from a repository stops being a link. Confirmed by reading the code and Python's documented
`mkstemp` behaviour. No test covers mode.

This reaches every io tool, `verify.write`'s repair, and `io.restore`.

## What to build

- `write_atomic` gives the temporary file the target's mode before the rename, when the target exists.
- A target that is a symlink is written at the file it points to, and the link stays.
- On Windows, the target's read-only flag is left as it is. `write.location` already refuses a read-only file.
- Tests on POSIX: a 0755 file stays 0755 after `write_atomic`, and a link stays a link with its target
  changed. They run on the macOS CI runner.

## Where

`lib/bytesio.py`, `tests/lib/test_bytesio.py`.

## Done when

- Both tests pass on the macOS runner, and the Windows suite is unchanged.
