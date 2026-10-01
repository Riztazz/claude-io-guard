"""Whether a shell command stops processes that other Claude Code sessions run too.

Two kinds of stop reach them. One names a shared runtime, such as python, node or pwsh, which every session's
servers and tools run in. The other picks processes by a match on their command line, which reaches whatever
matches, whoever started it. A stop by a literal id, by the id a port's owner gives, or by the name of one
application, such as an editor, reaches no other session's servers. The patterns read Bash and PowerShell
alike: the stop is found in the command with its strings and comments blanked, so a word in a message is
never the command, and the names it gives are read from the command itself at the same place.
"""
import re

RUNTIMES = re.compile(r"(?<![\w.-])(?:python[\d.]*w?|py|node|pwsh|powershell|bash|sh|cmd|claude|java|ruby"
                      r"|perl|deno|bun|uv)(?:\.exe)?(?![\w.-])", re.I)
NAMED = re.compile(r"\b(?:stop-process|spps|kill)\b[^;|\n]*?\s-(?:name|processname)\b[^;|\n]*"
                   r"|\btaskkill(?:\.exe)?\b[^;|\n]*?\s(?:/{1,2}|-)im\b[^;|\n]*"
                   r"|(?:^|(?<=[\s;&|(]))(?:pkill|killall)(?:\.exe)?\s+(?!(?-i:-f)\b)[^;|&\n]*"
                   r"|\b(?:get-process|gps)\b(?![^;|\n]*\s-id\b)[^;|\n]*"
                   r"(?:\|\s*(?:where-object|where|\?(?=[\s{]))[^;|\n]*)?\|\s*(?:stop-process|spps|kill)\b",
                   re.I)
MATCHED = re.compile(r"(?:^|(?<=[\s;&|(]))pkill\s+(?:-\S+\s+)*(?-i:-f)\b"
                     r"|\btaskkill\b[^;|\n]*?\s(?:/{1,2}|-)fi\b"
                     r"|\bwmic\b[^;|\n]*\bprocess\b[^;|\n]*\b(?:delete|call\s+terminate)\b", re.I)
LISTS = re.compile(r"\bwin32_process\b|\bpgrep\b|(?:^|(?<=[\s;&|(]))ps\s+(?:aux|-e|-ef|-A)\b", re.I)
NAME_FILTER = re.compile(r"\bname\s*(?:=|like)\s*'([^']*)'", re.I)
STOPS = re.compile(r"\b(?:stop-process|spps)\b(?![^;|\n]*\s-id\s+\d)"
                   r"|\btaskkill\b(?![^;|\n]*\s(?:/{1,2}|-)pid\s+\d)|\bxargs\s+(?:-\S+\s+)*kill\b"
                   r"|\bkill\s+(?:-\S+\s+)*\$\(|\.kill\(\)|\.terminate\(\)|-methodname\s+terminate\b", re.I)


def shown(text: str) -> str:
    """Blanked text for a message: one space between words, and no quote pair a blank string left."""
    return " ".join(re.sub(r"(['\"])\s*\1", " ", text).split())


MATCHERS = {"pkill": "pkill -f", "taskkill": "taskkill /FI", "wmic": "wmic"}


def broad_stop(command: str, code: str) -> str | None:
    """What command stops that other sessions run too, as "every python.exe process", or None. code is command
    with its strings and comments blanked, offset for offset."""
    for found in NAMED.finditer(code):
        runtime = RUNTIMES.search(command, found.start(), found.end())
        if runtime:
            return f"every {runtime[0]} process"
    matched = MATCHED.search(code)
    if matched:
        return f"every process {MATCHERS[matched[0].split()[0].lower()]} matches"
    listed, stopped = LISTS.search(code), STOPS.search(code)
    if not (listed and stopped) or one_application(command):
        return None
    return f"every process a {shown(listed[0])} match picks"


def one_application(command: str) -> bool:
    """Whether a Win32_Process listing's Name filter names applications only, and no shared runtime, as
    Name like 'UnrealEditor%' does."""
    names = [name.replace("%", "") for name in NAME_FILTER.findall(command)]
    return bool(names) and not any(RUNTIMES.search(name) for name in names)
