---
title: Catch quoting, escaping and dialect hazards before a command runs
stage: B
area: transport
created: 2026-09-27
status: open
depends-on: [08, 09, 11]
findings: [SHW-2, SHW-3, SHW-5, SHW-6, SHW-7, SHL-1, SHL-2, SHL-4, SHL-5, SHL-6, OUT-1]
platforms: [windows, macos]
commit: "feat: refuse commands whose quoting or dialect would change what runs"
---

## Why

Most shell failures are visible in the command text before it runs. Each one costs a round trip, and some change
what runs without an error. The baseline counts:

| Hazard | Count |
|---|---|
| Backtick failures | 2 |
| Trailing-backslash quotes | 17 |
| Python invalid-escape warnings | 72 |
| `unicodeescape` errors | 10 |
| PowerShell call operators sent to bash | 5 |

## What to build

A PreToolUse check on Bash and PowerShell, one rule per hazard. Every refusal carries a fix hint. A rule rewrites
the command only when the rewrite is mechanical, and every rewrite follows the rewrite mode from task 11 (D12).

- **`BACKTICK_IN_DOUBLE_QUOTES`:** backticks inside double quotes. Refuse, and suggest single quotes.
- **`TRAILING_BACKSLASH_QUOTE`:** a backslash right before a closing double quote in a path. Rewrite
  `"C:\x\"` to `"C:/x/"`.
- **`INLINE_SCRIPT_INVALID`:** compile each Python body, inline or moved, with `compile()` before it runs. Report
  a SyntaxError or a SyntaxWarning, such as an invalid escape or a `\U` inside a Windows path. Also flag
  `open(` without `encoding=`.
- **`DIALECT_MISMATCH`:** each shell's syntax sent to the other shell's tool.
  - PowerShell syntax in the Bash tool: the `&` call operator, `$env:`, `Get-*` cmdlets, here-strings.
  - Bash syntax in the PowerShell tool: `<<`, `tail`, `export`, and `&&` on Windows PowerShell 5.1.
- **PowerShell traps:**
  - When pwsh is present, parse the command with
    `[System.Management.Automation.Language.Parser]::ParseInput` first, through `lib/pwsh.py`.
  - Flag `Select-String -Recurse`.
  - Flag automatic variables such as `$Pid` used as names.
  - Flag native `-name:value` arguments.
- **`PIPE_HIDES_EXIT`:** a build, test or compile command piped into head, tail, grep or Select-Object. Warn only.
  A `set -o pipefail;` prefix would add a subcommand that no narrow allow rule matches, so the check never adds
  one.

## Where

`plugins/io-guard/scripts/ioguard/checks/lint.py`, `lib/pwsh.py`, `tests/checks/test_lint.py`.

## Done when

- Replay catches the recorded failures of each class above.
- For each rule, the hits on commands that succeeded are checked on a sample, and the false-refusal rate is under
  0.1%.
