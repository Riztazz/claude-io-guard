"""Read-only summaries of tx_events.jsonl.

    python tx_report.py tools            file tool calls and their error classes, per project
    python tools_examples <class> [n]    examples of one file-tool error class
    python tx_report.py shell            shell result and command pattern counts, per project
    python tx_report.py shell_examples <key> [n]
    python tx_report.py text <key> [n]   assistant sentences for one keyword
    python tx_report.py runs             the scratchpad scripts run most often
"""

import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS = os.path.join(HERE, "tx_events.jsonl")

ERROR_CLASSES = [
    ("not-found", re.compile(r"String to replace not found", re.I)),
    ("multiple-matches", re.compile(r"Found \d+ matches of the string to replace", re.I)),
    ("not-read-yet", re.compile(r"has not been read yet|Read it first", re.I)),
    ("modified-since-read", re.compile(r"modified since read|has been (?:unexpectedly )?modified", re.I)),
    ("same-strings", re.compile(r"No changes to make|old_string and new_string are (?:exactly )?the same", re.I)),
    ("too-many-tokens", re.compile(r"exceeds maximum allowed tokens|too large|exceeds maximum allowed size", re.I)),
    ("file-missing", re.compile(r"does not exist|ENOENT|no such file", re.I)),
    ("is-directory", re.compile(r"EISDIR|is a directory", re.I)),
    ("binary", re.compile(r"binary", re.I)),
    ("permission", re.compile(r"permission|denied|EPERM|EACCES|EBUSY|read-only", re.I)),
    ("user-rejected", re.compile(r"user doesn't want|rejected|The user (?:denied|declined)|was interrupted|Request interrupted", re.I)),
    ("hook-blocked", re.compile(r"hook", re.I)),
    ("invalid-input", re.compile(r"InputValidationError|invalid|required parameter|must be", re.I)),
    ("notebook", re.compile(r"notebook", re.I)),
]


def classify(text):
    for name, rx in ERROR_CLASSES:
        if rx.search(text):
            return name
    return "other"


def events():
    with open(EVENTS, encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def tools():
    total = collections.Counter()
    errors = collections.Counter()
    classes = collections.defaultdict(collections.Counter)
    for ev in events():
        if ev["ev"] != "tool":
            continue
        key = (ev["p"], ev["tool"])
        total[key] += 1
        if ev["err"] or "<tool_use_error>" in ev.get("res", ""):
            errors[key] += 1
            classes[ev["tool"]][classify(ev.get("res", ""))] += 1
    print("%-16s %-12s %8s %7s %6s" % ("project", "tool", "calls", "errors", "rate"))
    for key in sorted(total):
        rate = 100.0 * errors[key] / total[key]
        print("%-16s %-12s %8d %7d %5.1f%%" % (key[0], key[1], total[key], errors[key], rate))
    print()
    for tool, counter in classes.items():
        print(tool, dict(counter.most_common()))


def tools_examples(cls, n):
    shown = 0
    for ev in events():
        if ev["ev"] != "tool" or not (ev["err"] or "<tool_use_error>" in ev.get("res", "")):
            continue
        if classify(ev.get("res", "")) != cls:
            continue
        shown += 1
        print("=" * 90)
        print(ev["p"], ev["s"], ev["t"], ev["tool"], json.dumps(ev["inp"])[:900])
        print("RESULT:", ev["res"][:500])
        if shown >= n:
            break


def shell():
    hr = collections.defaultdict(collections.Counter)
    hc = collections.defaultdict(collections.Counter)
    total = collections.Counter()
    for ev in events():
        if ev["ev"] != "shell":
            continue
        total[ev["p"]] += 1
        for k in ev["hr"]:
            hr[k][ev["p"]] += 1
        for k in ev["hc"]:
            hc[k][ev["p"]] += 1
    print("result patterns")
    for k, c in sorted(hr.items(), key=lambda kv: -sum(kv[1].values())):
        print("  %-16s %5d %s" % (k, sum(c.values()), dict(c)))
    print("command patterns")
    for k, c in sorted(hc.items(), key=lambda kv: -sum(kv[1].values())):
        print("  %-22s %5d %s" % (k, sum(c.values()), dict(c)))


def shell_examples(key, n, errors_only):
    shown = 0
    for ev in events():
        if ev["ev"] != "shell":
            continue
        if key not in ev["hr"] and key not in ev["hc"]:
            continue
        if errors_only and not ev["err"]:
            continue
        shown += 1
        print("=" * 90)
        print(ev["p"], ev["s"], ev["t"], ev["tool"], "ERR" if ev["err"] else "ok")
        print("CMD:", ev["cmd"][:700])
        print("RES:", ev["res"][:600])
        if shown >= n:
            break


def text(key, n, needle):
    shown = 0
    for ev in events():
        if ev["ev"] != "text" or ev["k"] != key:
            continue
        if needle and not re.search(needle, ev["snip"], re.I):
            continue
        shown += 1
        print("-" * 90)
        print(ev["p"], ev["s"], ev["t"])
        print(ev["snip"].replace("\n", " "))
        if shown >= n:
            break


def text_counts():
    c = collections.defaultdict(collections.Counter)
    for ev in events():
        if ev["ev"] == "text":
            c[ev["k"]][ev["p"]] += 1
    for k, counter in c.items():
        print("%-12s %5d %s" % (k, sum(counter.values()), dict(counter)))


def runs():
    c = collections.Counter()
    per = collections.Counter()
    for ev in events():
        if ev["ev"] == "run":
            per[ev["p"]] += 1
            for s in ev["scripts"]:
                c[s] += 1
    print(dict(per))
    for name, count in c.most_common(60):
        print("%4d %s" % (count, name))


if __name__ == "__main__":
    mode = sys.argv[1]
    arg = sys.argv[2] if len(sys.argv) > 2 else ""
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    if mode == "tools":
        tools()
    elif mode == "tools_examples":
        tools_examples(arg, count)
    elif mode == "shell":
        shell()
    elif mode == "shell_examples":
        shell_examples(arg, count, "--err" in sys.argv)
    elif mode == "text":
        text(arg, count, sys.argv[4] if len(sys.argv) > 4 else "")
    elif mode == "text_counts":
        text_counts()
    elif mode == "runs":
        runs()
