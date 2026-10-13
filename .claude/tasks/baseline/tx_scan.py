"""One pass over the four projects' transcripts. Writes tx_events.jsonl next to this file.

Each event is one of:
  tool   - a file tool call (Edit, MultiEdit, Write, Read, NotebookEdit, Grep, Glob) with its result
  shell  - a Bash or PowerShell call whose command or result matches a file-handling pattern
  run    - a Bash or PowerShell call that runs a scratchpad script
  text   - an assistant sentence that names a file-handling problem
"""

import glob
import json
import os
import re
import sys

ROOT = r"C:\Users\felia\.claude\projects"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tx_events.jsonl")

PROJECTS = {
    "C--Users-felia-Desktop-projs-unreal-CLICKER": "CLICKER",
    "C--Users-felia-Desktop-projs-unreal-CLICKER--claude-worktrees-optimistic-tu-424662": "CLICKER",
    "C--Users-felia-Desktop-projs-unreal-CLICKER--claude-worktrees-pensive-dhawan-f437ba": "CLICKER",
    "C--Users-felia-Desktop-projs-unreal-OrbitalDrift": "OrbitalDrift",
    "C--Users-felia-Desktop-projs-unreal-SmartTablesHost": "SmartTablesHost",
    "C--Users-felia-Desktop-projs-unreal-UNREAL-SHARED": "UNREAL-SHARED",
}

FILE_TOOLS = {"Edit", "MultiEdit", "Write", "Read", "NotebookEdit", "Grep", "Glob"}
SHELL_TOOLS = {"Bash", "PowerShell"}

SHELL_RESULT = [
    ("heredoc-eof", re.compile(r"here-document at line \d+ delimited by end-of-file|wanted [`']\w+'", re.I)),
    ("unexpected-eof", re.compile(r"unexpected EOF while looking for matching|unexpected end of file", re.I)),
    ("bash-syntax", re.compile(r"syntax error near unexpected token", re.I)),
    ("guard-refused", re.compile(r"shell-write-guard refused|write-guard", re.I)),
    ("ps-terminator", re.compile(r"string is missing the terminator|Missing closing|Unexpected token|ParserError|The here-string", re.I)),
    ("unicode-error", re.compile(r"Unicode(?:En|De)codeError|charmap. codec|codec can't (?:en|de)code", re.I)),
    ("unicodeescape", re.compile(r"unicodeescape|truncated \\UXXXXXXXX", re.I)),
    ("py-syntax", re.compile(r"SyntaxError|IndentationError|TabError|unterminated (?:string|triple)|EOL while scanning|unexpected character after line continuation", re.I)),
    ("escape-warning", re.compile(r"invalid escape sequence", re.I)),
    ("git-eol", re.compile(r"(?:LF|CRLF) will be replaced by (?:CRLF|LF)|in the working copy of .* (?:LF|CRLF)", re.I)),
    ("msys-path", re.compile(r"Program Files/Git/|C:/Program Files/Git", re.I)),
    ("backslash-path", re.compile(r"\bC:Users|Usersfelia|Desktopprojs", re.I)),
    ("file-locked", re.compile(r"WinError 32|being used by another process|Device or resource busy|Permission denied|Access is denied|read-only", re.I)),
    ("no-such-file", re.compile(r"No such file or directory|cannot find (?:the )?path|does not exist|FileNotFoundError|Cannot find path", re.I)),
    ("null-bytes", re.compile(r"\\x00|\x00|UTF-16|\xff\xfe|\u00ff\u00fe", re.I)),
    ("bom", re.compile(r"\ufeff|\\ufeff|\bBOM\b|utf-8-sig|\xef\xbb\xbf", re.I)),
    ("truncated", re.compile(r"Output too large|output truncated|\[truncated|lines truncated", re.I)),
]

SHELL_COMMAND = [
    ("cmd-heredoc", re.compile(r"<<-?\s*['\"]?\w+")),
    ("cmd-python-c", re.compile(r"\bpython[0-9.]*(?:\.exe)?\s+-c\s", re.I)),
    ("cmd-sed-i", re.compile(r"\bsed\b[^\n|;&]*\s-[a-zA-Z]*i\b|\bperl\s+-[a-zA-Z]*i")),
    ("cmd-redirect-src", re.compile(r">{1,2}\s*['\"]?[^\s|;&<>]+\.(?:h|cpp|cs|py|md|ini|json|ps1|uplugin|uproject)\b", re.I)),
    ("cmd-here-string", re.compile(r"@['\"]\s*\r?\n")),
    ("cmd-set-content", re.compile(r"\b(?:Set-Content|Add-Content|Out-File|WriteAllText|WriteAllLines|WriteAllBytes)\b", re.I)),
    ("cmd-unix2dos", re.compile(r"\b(?:unix2dos|dos2unix)\b", re.I)),
    ("cmd-git-checkout-file", re.compile(r"git (?:checkout|restore)\s+(?:--\s+)?\S+\.\w+", re.I)),
]

TEXT_KEYS = [
    ("crlf", re.compile(r"\bCRLF\b|line[- ]ending|\\r\\n|carriage return", re.I)),
    ("tabs", re.compile(r"\btabs?\b.{0,40}\bspaces?\b|\bspaces?\b.{0,40}\btabs?\b|indentation", re.I)),
    ("edit-tool", re.compile(r"\bEdit tool\b|\bold_string\b|String to replace|\bEdit (?:failed|refused|cannot|can't|won't)", re.I)),
    ("write-tool", re.compile(r"\bWrite tool\b", re.I)),
    ("read-tool", re.compile(r"\bRead tool\b|has not been read|modified since read|exceeds maximum allowed tokens", re.I)),
    ("heredoc", re.compile(r"heredoc|here-doc|here-string|here string", re.I)),
    ("mangle", re.compile(r"mangl|corrupt|garbl|clobber|truncat", re.I)),
    ("encoding", re.compile(r"\bBOM\b|UTF-16|encoding|mojibake|non-ASCII|cp1252", re.I)),
    ("escape", re.compile(r"backslash|escap", re.I)),
    ("script-edit", re.compile(r"(?:edit|patch|splice)\w* script|script (?:to|that) (?:edit|patch|write|rewrite)", re.I)),
]


def project_of(path):
    rel = os.path.relpath(path, ROOT)
    return PROJECTS.get(rel.split(os.sep)[0])


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts)
    return ""


def flags_of(s):
    if not isinstance(s, str):
        return {}
    lines = s.split("\n")
    return {
        "tab": "\t" in s,
        "cr": "\r" in s,
        "lead_sp": any(re.match(r"^ {2,}\S", l) for l in lines),
        "lead_tab": any(l.startswith("\t") for l in lines),
        "nonascii": any(ord(c) > 127 for c in s),
        "trail_ws": any(re.search(r"[ \t]+$", l) for l in lines),
        "len": len(s),
        "lines": len(lines),
    }


def summarise_input(name, inp):
    if not isinstance(inp, dict):
        return {}
    out = {"file": inp.get("file_path") or inp.get("notebook_path") or inp.get("path") or ""}
    if name == "Edit":
        out["old"] = (inp.get("old_string") or "")[:600]
        out["old_f"] = flags_of(inp.get("old_string"))
        out["new_f"] = flags_of(inp.get("new_string"))
        out["all"] = bool(inp.get("replace_all"))
    elif name == "MultiEdit":
        edits = inp.get("edits") or []
        out["n"] = len(edits)
        out["old"] = [(e.get("old_string") or "")[:300] for e in edits[:4]]
    elif name == "Write":
        out["content_f"] = flags_of(inp.get("content"))
        out["head"] = (inp.get("content") or "")[:160]
    elif name == "Read":
        out["offset"] = inp.get("offset")
        out["limit"] = inp.get("limit")
    elif name in ("Grep", "Glob"):
        out["pattern"] = (inp.get("pattern") or "")[:200]
    return out


def main():
    files = []
    for d in PROJECTS:
        files += glob.glob(os.path.join(ROOT, d, "**", "*.jsonl"), recursive=True)
    files.sort(key=os.path.getsize)
    written = 0
    with open(OUT, "w", encoding="utf-8") as out:
        for fi, path in enumerate(files):
            project = project_of(path)
            sidechain = os.sep + "subagents" + os.sep in path
            session = os.path.basename(path)[:8]
            uses = {}
            try:
                handle = open(path, encoding="utf-8", errors="replace")
            except OSError:
                continue
            with handle:
                for line in handle:
                    if '"tool_use"' not in line and '"tool_result"' not in line and '"text"' not in line:
                        continue
                    try:
                        entry = json.loads(line)
                    except ValueError:
                        continue
                    msg = entry.get("message") or {}
                    content = msg.get("content")
                    stamp = (entry.get("timestamp") or "")[:16]
                    if not isinstance(content, list):
                        continue
                    role = msg.get("role") or entry.get("type")
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        kind = block.get("type")
                        if kind == "tool_use":
                            uses[block.get("id")] = (block.get("name"), block.get("input"), stamp)
                        elif kind == "tool_result":
                            use = uses.pop(block.get("tool_use_id"), None)
                            if not use:
                                continue
                            name, inp, use_stamp = use
                            result = text_of(block.get("content"))
                            is_error = bool(block.get("is_error"))
                            base = {"p": project, "s": session, "side": sidechain, "t": use_stamp, "tool": name,
                                    "err": is_error}
                            if name in FILE_TOOLS:
                                ev = dict(base, ev="tool", inp=summarise_input(name, inp),
                                          res=result[:700] if (is_error or "<tool_use_error>" in result) else "")
                                out.write(json.dumps(ev) + "\n")
                                written += 1
                            elif name in SHELL_TOOLS:
                                command = (inp or {}).get("command") or ""
                                hits_r = [k for k, rx in SHELL_RESULT if rx.search(result)]
                                hits_c = [k for k, rx in SHELL_COMMAND if rx.search(command)]
                                runs = re.findall(r"scratchpad[/\\]+([\w.\-]+\.(?:py|ps1|sh|js))", command)
                                if hits_r or hits_c:
                                    ev = dict(base, ev="shell", hr=hits_r, hc=hits_c, cmd=command[:900],
                                              res=result[:900])
                                    out.write(json.dumps(ev) + "\n")
                                    written += 1
                                if runs:
                                    ev = dict(base, ev="run", scripts=runs[:5], res=result[:300] if is_error else "")
                                    out.write(json.dumps(ev) + "\n")
                                    written += 1
                        elif kind == "text" and role == "assistant":
                            text = block.get("text") or ""
                            for key, rx in TEXT_KEYS:
                                for m in rx.finditer(text):
                                    a = max(0, m.start() - 260)
                                    b = min(len(text), m.end() + 260)
                                    ev = {"p": project, "s": session, "side": sidechain, "t": stamp, "ev": "text",
                                          "k": key, "snip": text[a:b]}
                                    out.write(json.dumps(ev) + "\n")
                                    written += 1
                                    break
            if fi % 50 == 0:
                sys.stdout.write("%d/%d files, %d events\n" % (fi, len(files), written))
                sys.stdout.flush()
    print("done", len(files), "files", written, "events ->", OUT)


if __name__ == "__main__":
    main()
