"""Read-only byte survey of the tracked text files in each repository.

Per extension: files that are CRLF, LF, mixed, with a BOM, not valid UTF-8, with non-ASCII bytes, indented by
tab, by spaces, or by both, and with no final newline. Plus each repository's git line-ending settings.
"""

import collections
import os
import re
import subprocess

REPOS = {
    "CLICKER": r"C:\Users\felia\Desktop\projs\unreal\CLICKER",
    "OrbitalDrift": r"C:\Users\felia\Desktop\projs\unreal\OrbitalDrift",
    "SmartTablesHost": r"C:\Users\felia\Desktop\projs\unreal\SmartTablesHost",
    "UNREAL-SHARED": r"C:\Users\felia\Desktop\projs\unreal\UNREAL-SHARED",
}
TEXT = {".h", ".cpp", ".cs", ".py", ".md", ".ini", ".json", ".uplugin", ".uproject", ".ps1", ".txt", ".usf", ".ush",
        ".inl", ".js", ".html", ".css", ".template"}


def git(repo, *args):
    return subprocess.run(["git", "-C", repo] + list(args), capture_output=True).stdout.decode("utf-8", "replace")


def survey(name, repo):
    settings = {key: git(repo, "config", "--get", key).strip() or "-" for key in ("core.autocrlf", "core.eol")}
    attributes = os.path.join(repo, ".gitattributes")
    eol_rules = []
    if os.path.exists(attributes):
        eol_rules = [l.strip() for l in open(attributes, encoding="utf-8", errors="replace") if "eol" in l or "text" in l]
    editorconfig = os.path.join(repo, ".editorconfig")
    ec = []
    if os.path.exists(editorconfig):
        ec = [l.strip() for l in open(editorconfig, encoding="utf-8", errors="replace") if re.match(r"\s*(end_of_line|indent_style|charset)", l)]
    print("=" * 100)
    print("%s  autocrlf=%s eol=%s  .gitattributes eol/text rules=%s  .editorconfig=%s"
          % (name, settings["core.autocrlf"], settings["core.eol"], eol_rules[:4] or "none", ec[:6] or "none"))
    files = [f for f in git(repo, "ls-files", "-z").split("\0") if f]
    stats = collections.defaultdict(collections.Counter)
    for rel in files:
        ext = os.path.splitext(rel)[1].lower()
        if ext not in TEXT:
            continue
        path = os.path.join(repo, rel)
        try:
            data = open(path, "rb").read()
        except OSError:
            continue
        s = stats[ext]
        s["files"] += 1
        crlf = data.count(b"\r\n")
        lf = data.count(b"\n") - crlf
        lone_cr = data.count(b"\r") - crlf
        if crlf and lf:
            s["mixed"] += 1
        elif crlf:
            s["crlf"] += 1
        elif lf:
            s["lf"] += 1
        if lone_cr:
            s["lone_cr"] += 1
        if data.startswith(b"\xef\xbb\xbf"):
            s["bom"] += 1
        if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
            s["utf16"] += 1
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            s["not_utf8"] += 1
        if any(b > 127 for b in data[3 if data.startswith(b"\xef\xbb\xbf") else 0:]):
            s["non_ascii"] += 1
        if b"\x00" in data:
            s["nul"] += 1
        if data and not data.endswith(b"\n"):
            s["no_final_nl"] += 1
        tab = len(re.findall(rb"^\t", data, re.M))
        space = len(re.findall(rb"^ {2,}\S", data, re.M))
        if tab and space:
            s["indent_both"] += 1
        elif tab:
            s["indent_tab"] += 1
        elif space:
            s["indent_space"] += 1
        if re.search(rb"[ \t]+\r?$", data, re.M):
            s["trailing_ws"] += 1
    keys = ["files", "crlf", "lf", "mixed", "lone_cr", "bom", "utf16", "not_utf8", "non_ascii", "nul", "no_final_nl",
            "indent_tab", "indent_space", "indent_both", "trailing_ws"]
    print("%-10s" % "ext" + "".join("%11s" % k for k in keys))
    for ext in sorted(stats, key=lambda e: -stats[e]["files"]):
        print("%-10s" % ext + "".join("%11d" % stats[ext][k] for k in keys))


for name, repo in REPOS.items():
    survey(name, repo)
