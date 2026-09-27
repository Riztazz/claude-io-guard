---
title: Detect a file's byte profile
stage: C
area: bytes
created: 2026-09-27
status: open
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
