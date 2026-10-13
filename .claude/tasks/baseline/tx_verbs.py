"""Read-only. What the Bash and PowerShell calls were used for, by the first command of each segment.

    python tx_verbs.py      prints the category shares per tool and the top verbs of each category
"""

import collections
import glob
import json
import os
import re

ROOT = r"C:\Users\felia\.claude\projects"
DIRS = ["C--Users-felia-Desktop-projs-unreal-CLICKER", "C--Users-felia-Desktop-projs-unreal-OrbitalDrift",
        "C--Users-felia-Desktop-projs-unreal-SmartTablesHost", "C--Users-felia-Desktop-projs-unreal-UNREAL-SHARED",
        "C--Users-felia-Desktop-projs-unreal-CLICKER--claude-worktrees-optimistic-tu-424662",
        "C--Users-felia-Desktop-projs-unreal-CLICKER--claude-worktrees-pensive-dhawan-f437ba"]

CATEGORIES = [
    ("inspect", {"cat", "head", "tail", "grep", "rg", "ls", "find", "wc", "diff", "file", "od", "xxd", "stat", "du",
                 "pwd", "echo", "printf", "awk", "sort", "uniq", "cut", "tr", "basename", "dirname", "realpath",
                 "Get-Content", "Get-ChildItem", "Select-String", "Test-Path", "Get-Item", "dir", "type", "less",
                 "Measure-Object", "Format-Hex", "Resolve-Path", "Write-Output", "Write-Host", "cmp", "md5sum",
                 "sha1sum", "sha256sum", "Get-FileHash", "tree", "which", "where", "Get-Command", "date", "sed"}),
    ("git", {"git", "gh"}),
    ("python", {"python", "python3", "py", "python.exe"}),
    ("build-run", {"build.py", "editor.py", "UnrealEditor.exe", "UnrealEditor-Cmd.exe", "Build.bat", "RunUAT.bat",
                   "dotnet", "msbuild", "MSBuild.exe", "cmake", "ninja", "clang-format", "clang-format.exe", "node",
                   "npm", "npx", "pwsh", "powershell", "powershell.exe", "cmd", "cmd.exe", "bash", "sh", "&", "."}),
    ("mutate", {"cp", "mv", "rm", "mkdir", "touch", "tee", "rmdir", "ln", "chmod", "Copy-Item", "Move-Item",
                "Remove-Item", "New-Item", "Set-Content", "Add-Content", "Out-File", "Rename-Item", "unzip", "tar"}),
    ("process", {"ps", "tasklist", "taskkill", "kill", "sleep", "Start-Sleep", "Get-Process", "Stop-Process",
                 "Start-Process", "wmic", "Wait-Process", "timeout"}),
    ("net", {"curl", "wget", "Invoke-WebRequest", "Invoke-RestMethod"}),
]
LOOKUP = {verb.lower(): name for name, verbs in CATEGORIES for verb in verbs}


def segments(command):
    body = re.sub(r"<<-?\s*(['\"]?)(\w+)\1.*?^\2\s*$", " HEREDOC ", command, flags=re.S | re.M)
    for part in re.split(r"&&|\|\||;|\n|\|", body):
        part = part.strip()
        if part:
            yield part


def verb_of(part):
    tokens = part.split()
    while tokens and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", tokens[0]) or tokens[0] in ("export", "time", "env",
                                                                                         "sudo", "exec", "(", "{")):
        tokens = tokens[1:]
    if not tokens:
        return None
    word = tokens[0].strip("'\"()")
    if word in ("cd", "Set-Location", "pushd", "popd", "set", "$ErrorActionPreference"):
        return "cd"
    base = re.split(r"[\\/]", word)[-1]
    if base.lower().startswith("python"):
        return "python"
    if base.endswith(".py") or base.endswith(".sh") or base.endswith(".ps1"):
        return base
    return base


def category(verb, part):
    if verb is None or verb == "cd":
        return None
    if verb == "sed" and re.search(r"\s-[a-zA-Z]*i\b", part):
        return "mutate"
    if verb.endswith(".py") or verb.endswith(".sh") or verb.endswith(".ps1"):
        return "build-run" if verb in ("build.py", "editor.py") else "script"
    if re.search(r">{1,2}\s*[^&\s]", part) and not re.search(r">\s*/dev/null|2>&1|>\s*\$null", part):
        return "mutate"
    return LOOKUP.get(verb.lower(), "other")


def main():
    per_tool = collections.defaultdict(collections.Counter)
    first_cat = collections.defaultdict(collections.Counter)
    verbs = collections.defaultdict(collections.Counter)
    for d in DIRS:
        for path in glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True):
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if '"tool_use"' not in line or ('"Bash"' not in line and '"PowerShell"' not in line):
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    content = (entry.get("message") or {}).get("content")
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if not isinstance(block, dict) or block.get("type") != "tool_use":
                            continue
                        tool = block.get("name")
                        if tool not in ("Bash", "PowerShell"):
                            continue
                        command = (block.get("input") or {}).get("command") or ""
                        cats = []
                        for part in segments(command):
                            v = verb_of(part)
                            c = category(v, part)
                            if c:
                                cats.append(c)
                                verbs[c][v] += 1
                        per_tool[tool]["calls"] += 1
                        for c in set(cats):
                            per_tool[tool][c] += 1
                        if cats:
                            first_cat[tool][cats[0]] += 1
                        if cats and all(c == "inspect" for c in cats):
                            per_tool[tool]["inspect-only"] += 1
    for tool, counter in per_tool.items():
        calls = counter["calls"]
        print("%s: %d calls" % (tool, calls))
        for c, n in counter.most_common():
            if c != "calls":
                print("   %-13s %6d  %5.1f%% of calls contain it" % (c, n, 100.0 * n / calls))
    print()
    for c, counter in verbs.items():
        print("%-10s top verbs: %s" % (c, ", ".join("%s %d" % kv for kv in counter.most_common(14))))


if __name__ == "__main__":
    main()
