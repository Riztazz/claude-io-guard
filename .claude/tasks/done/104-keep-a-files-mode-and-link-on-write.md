---
title: Keep a file's mode and its symlink when io-guard writes it
stage: I
area: lib
created: 2026-09-29
status: done
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

## What changed

- `lib/bytesio.py`: `write_atomic` writes a path that is a symlink at the file `os.path.realpath` names, so
  the link stays, and on POSIX gives the temporary file the old file's mode with `os.chmod` before the
  rename. The `WriteReport` names the path it was given.
- `tests/lib/test_bytesio.py`: a 0755 file stays 0755, and a symlink stays a link while its target gets
  the new bytes. Both run on POSIX only.
- **Not checked yet:** both tests are skipped on Windows, where this machine cannot make a symlink without
  admin rights (`WinError 1314`) and a file has no mode bits. So neither was seen failing before the change
  or passing after it. The macOS CI runner runs both on the next push, and its result is the check. The
  Windows suite is unchanged, 996 with 2 skipped.
- Docs: `docs/design/architecture.md` (`write_atomic`).
- Checked on Windows on 2026-09-29, where the change is inert. macOS waits for CI.
