---
title: Detect a file's byte profile
stage: C
area: bytes
created: 2026-09-27
status: done
claimed-by: claude-opus-5-5, session 7eeb509f
depends-on: [05, 07]
findings: [BYT-4, BYT-5, BYT-6, BYT-11, ANC-5, INP-4]
platforms: [windows, macos]
commit: "feat: read a file's endings, BOM, encoding and indent from its bytes"
---

## Why

Every byte check compares a write against the file's own convention. One repository can hold several conventions:

| Repository | Mixed convention |
|---|---|
| CLICKER | 102 LF C++ files among 2,643 |
| OrbitalDrift | 31 BOM files among 2,286 |
| Several repos | Tabs and spaces in the same repository (`context.md`) |

Shell tools misreport CR (BYT-5), so the profile reads raw bytes.

## What to build

`lib/profile.py`, with the types in `docs/design/architecture.md`, section 2, "Profile".

**`profile(data: bytes) -> Profile`** reports:

- **Endings:** counts of CRLF, bare LF and lone CR, the dominant style, and whether the file mixes them.
- **BOM:** UTF-8, UTF-16 LE, UTF-16 BE, or none.
- **Encoding:** valid UTF-8 or not. When not, the position of the first invalid bytes and a cp1250 or cp1252
  guess.
- **Shape:** whether the file has a final newline, the line count and the size.
- **Indent:** lines indented by tabs, by spaces, or by both. The space width.
- **Counts:** NUL and other C0 control bytes, U+FFFD, private-use glyphs, non-ASCII characters, and lines with
  trailing whitespace.
- **Binary sniff:** a NUL byte in the first 8 KB, instead of trusting the file extension (INP-4).
- **`Profile.line()`** for the one-line summary, such as `CRLF, BOM, UTF-8, tabs, 1,284 lines`.

It must profile 1 MB in under 20 ms.

**`target_profile(path, siblings, editorconfig, gitattributes)`** gives the convention a new file should take. It
reads `.editorconfig` first, then `.gitattributes`, then the majority of sibling files with the same extension.

## Where

`plugins/io-guard/scripts/ioguard/lib/profile.py`, `tests/lib/test_profile.py`.

## Done when

- Every fixture from task 05 profiles correctly in CI on both platforms.
- Profiles of the four repositories' files match the survey from `baseline/repo_bytes.py`.

## What changed

- **`lib/profile.py`, new:** `profile(data)` and `target_profile(siblings, editorconfig, gitattributes)`, with
  the types of `architecture.md`, section 2, and `EolCounts.dominant` for a mixed file.
  - The style comes from the CRLF and LF counts, as the survey counted them. A lone CR is counted and warned
    about, and makes the style `CR` only in a file with no other ending.
  - A UTF-16 file is counted in its UTF-8 form, so its own NUL bytes neither count nor mark it binary.
  - Invalid UTF-8 gets the offset of its first bad byte, and a cp1250 or cp1252 guess from how many high bytes
    read as Central European letters.
  - The indent width is the largest of 8, 4, 3 and 2 that 80% of the space-indented lines sit on.
  - `line()` gives one line such as `CRLF, BOM, UTF-8, tabs, 1,284 lines`, and `warnings()` one sentence per
    hazard: mixed endings, a lone CR, invalid UTF-8, NUL, control bytes, U+FFFD and private-use glyphs.
- **`target_profile` takes no `path`.** The caller resolves `.editorconfig`, `.gitattributes` and the siblings
  for the path, so the path told it nothing more. `architecture.md` changes with it.
- **Not built here:** `convert_eol` and `with_bom`, which `architecture.md` lists under `profile.py`. Task 17
  is the first to use them, and `architecture.md` now marks them for it.
- **Tests, 378 in all, up from 363:** `tests/lib/test_profile.py` (15), over every task 05 fixture.
- **Docs:** `docs/design/architecture.md` section 2 (the profile's rules and speed, `dominant`,
  `target_profile`) and section 4, and `context.md` (the survey match). The README, the drawing and `CLAUDE.md`
  need nothing, because nothing yet shows a profile to a user.

Evidence, on Windows 10 with Python 3.14.0 on 2026-09-27:

- **The four repositories:** 5,955 tracked text files profiled, read-only, and compared with the survey's own
  rules, file by file, for endings, BOM, UTF-8, NUL, final newline, indent and trailing whitespace. No file
  differs.
- **Speed, best of 20 runs on 1 MB:** 10.9 ms for workbench C++ and 8.1 ms for Polish UTF-8, against the 20 ms
  budget. A first draft took 35.5 ms, with 30 ms of it in line-anchored regexes, and byte counts replace them.
- **Every task 05 fixture** has its expected profile in a test, which CI runs on Windows and macOS.
- `python -m unittest discover -s tests -t .` ran 378 tests, all passing. The profile tests also pass with
  POSIX paths, as a Mac builds them.

Not checked:

- **The timing on macOS.** CI runs a loose bound of 0.5 s, and only this machine measured the 11 ms.
