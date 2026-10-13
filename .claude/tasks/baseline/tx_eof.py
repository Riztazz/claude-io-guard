"""Read-only. Full commands of the Bash calls whose result says "unexpected EOF while looking for matching".

    python tx_eof.py stats            per failing heredoc: lines, bytes, apostrophes, backslashes, and the
                                      same numbers for heredocs that passed, for comparison
    python tx_eof.py show <n>         print failing command number n in full
"""

import glob
import json
import os
import re
import sys

ROOT = r"C:\Users\felia\.claude\projects"
DIRS = ["C--Users-felia-Desktop-projs-unreal-CLICKER", "C--Users-felia-Desktop-projs-unreal-OrbitalDrift",
        "C--Users-felia-Desktop-projs-unreal-SmartTablesHost", "C--Users-felia-Desktop-projs-unreal-UNREAL-SHARED",
        "C--Users-felia-Desktop-projs-unreal-CLICKER--claude-worktrees-optimistic-tu-424662",
        "C--Users-felia-Desktop-projs-unreal-CLICKER--claude-worktrees-pensive-dhawan-f437ba"]
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")


def calls():
    for d in DIRS:
        for path in glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True):
            uses = {}
            with open(path, encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if '"Bash"' not in line and '"tool_result"' not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    content = (entry.get("message") or {}).get("content")
                    if not isinstance(content, list):
                        continue
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use" and block.get("name") == "Bash":
                            uses[block.get("id")] = ((block.get("input") or {}).get("command") or "",
                                                     entry.get("timestamp", "")[:16], os.path.basename(path))
                        elif block.get("type") == "tool_result" and block.get("tool_use_id") in uses:
                            command, stamp, name = uses.pop(block.get("tool_use_id"))
                            result = block.get("content")
                            if isinstance(result, list):
                                result = "\n".join(b.get("text", "") for b in result if isinstance(b, dict))
                            yield command, str(result or ""), stamp, name, d


def measure(command):
    m = HEREDOC.search(command)
    if not m:
        return None
    quoted = bool(m.group(1))
    tag = m.group(2)
    body_start = command.find("\n", m.end())
    end = re.search(r"^%s\s*$" % re.escape(tag), command[body_start + 1:], re.M) if body_start >= 0 else None
    body = command[body_start + 1: body_start + 1 + end.start()] if end else command[body_start + 1:]
    return {
        "quoted": quoted,
        "closed": bool(end),
        "lines": body.count("\n") + 1,
        "bytes": len(body.encode("utf-8")),
        "apos": body.count("'"),
        "bslash": body.count("\\"),
        "dbl_bslash": body.count("\\\\"),
        "bslash_apos": body.count("\\'"),
        "backtick": body.count("`"),
        "in_subst": "$(" in command[:m.start()],
        "total_bytes": len(command.encode("utf-8")),
    }


def main():
    mode = sys.argv[1]
    failing, passing = [], []
    for command, result, stamp, name, d in calls():
        info = measure(command)
        if info is None:
            continue
        if "unexpected EOF while looking for matching" in result:
            failing.append((info, command, result, stamp, name))
        elif "Exit code" not in result[:20] and len(passing) < 20000:
            passing.append(info)
    if mode == "stats":
        def row(label, items):
            if not items:
                print(label, "none")
                return
            n = len(items)
            def share(key):
                return 100.0 * sum(1 for i in items if i[key]) / n
            lines = sorted(i["lines"] for i in items)
            size = sorted(i["total_bytes"] for i in items)
            print("%-8s n=%-6d quoted=%3.0f%% closed=%3.0f%% lines p50=%d p90=%d max=%d  bytes p50=%d p90=%d  "
                  "apos=%3.0f%% bslash=%3.0f%% dbl_bslash=%3.0f%% bslash_apos=%3.0f%% backtick=%3.0f%% in_$(=%3.0f%%"
                  % (label, n, share("quoted"), share("closed"), lines[n // 2], lines[int(n * 0.9)], lines[-1],
                     size[n // 2], size[int(n * 0.9)], share("apos"), share("bslash"), share("dbl_bslash"),
                     share("bslash_apos"), share("backtick"), share("in_subst")))
        row("failing", [f[0] for f in failing])
        row("passing", passing)
        for low, high in ((0, 30), (30, 60), (60, 100), (100, 200), (200, 100000)):
            f = sum(1 for x in failing if low <= x[0]["lines"] < high)
            p = sum(1 for x in passing if low <= x["lines"] < high)
            print("lines %4d-%-6d failing %4d  passing %6d  fail rate %.1f%%" % (low, high, f, p, 100.0 * f / max(1, f + p)))
        for key in ("bslash_apos", "dbl_bslash", "backtick", "in_subst"):
            f = sum(1 for x in failing if x[0][key])
            p = sum(1 for x in passing if x[key])
            print("%-12s failing %4d  passing %6d  fail rate %.1f%%" % (key, f, p, 100.0 * f / max(1, f + p)))
    elif mode == "show":
        info, command, result, stamp, name = failing[int(sys.argv[2])]
        print(stamp, name, json.dumps(info))
        print(result[:300])
        for i, line in enumerate(command.split("\n"), 1):
            print("%4d| %s" % (i, line))


if __name__ == "__main__":
    main()
