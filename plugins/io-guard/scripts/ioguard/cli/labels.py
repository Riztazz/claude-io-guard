"""The labels the corpus puts on a recorded call, from the rules the baseline of 2026-09-27 measured with.

A shell call gets one label per result rule its output matches, and a cmd- label per command shape. A file
tool call that failed gets the class of its error. Task 31 counts the same labels after io-guard ships, so a
rule here changes only with a note in both reports.
"""
import re

from ioguard.lib.text import BOM_CHAR

SHELLS = frozenset({"Bash", "PowerShell"})
BACKSLASH = chr(92)


def any_of(*literals: str) -> str:
    return "|".join(re.escape(literal) for literal in literals)


SHELL_RESULT: tuple[tuple[str, re.Pattern], ...] = (
    ("heredoc-eof", re.compile(r"here-document at line \d+ delimited by end-of-file|wanted [`']\w+'", re.I)),
    ("unexpected-eof", re.compile(r"unexpected EOF while looking for matching|unexpected end of file", re.I)),
    ("bash-syntax", re.compile(r"syntax error near unexpected token", re.I)),
    ("hook-refused", re.compile(r"PreToolUse:\w+ hook error")),
    ("ps-terminator", re.compile(r"string is missing the terminator|Missing closing|Unexpected token"
                                 r"|ParserError|The here-string", re.I)),
    ("unicode-error", re.compile(r"Unicode(?:En|De)codeError|charmap. codec|codec can't (?:en|de)code",
                                 re.I)),
    ("unicodeescape", re.compile(r"unicodeescape|truncated " + re.escape(BACKSLASH) + "UXXXXXXXX", re.I)),
    ("py-syntax", re.compile(r"SyntaxError|IndentationError|TabError|unterminated (?:string|triple)"
                             r"|EOL while scanning|unexpected character after line continuation", re.I)),
    ("escape-warning", re.compile(r"invalid escape sequence", re.I)),
    ("git-eol", re.compile(r"(?:LF|CRLF) will be replaced by (?:CRLF|LF)"
                           r"|in the working copy of .* (?:LF|CRLF)", re.I)),
    ("msys-path", re.compile(r"Program Files/Git/|C:/Program Files/Git", re.I)),
    ("backslash-path", re.compile(r"\b[A-Za-z]:Users[^\s/" + re.escape(BACKSLASH) + "]")),
    ("file-locked", re.compile(r"WinError 32|being used by another process|Device or resource busy"
                               r"|Permission denied|Access is denied|read-only", re.I)),
    ("no-such-file", re.compile(r"No such file or directory|cannot find (?:the )?path|does not exist"
                                r"|FileNotFoundError|Cannot find path", re.I)),
    ("null-bytes", re.compile(any_of(BACKSLASH + "x00", chr(0), chr(0xFF) + chr(0xFE)) + "|UTF-16", re.I)),
    ("bom", re.compile(any_of(BOM_CHAR, BACKSLASH + "ufeff", chr(0xEF) + chr(0xBB) + chr(0xBF))
                       + r"|\bBOM\b|utf-8-sig", re.I)),
    ("truncated", re.compile(r"Output too large|output truncated|\[truncated|lines truncated", re.I)),
)

SHELL_COMMAND: tuple[tuple[str, re.Pattern], ...] = (
    ("cmd-heredoc", re.compile(r"<<-?\s*['\"]?\w+")),
    ("cmd-python-c", re.compile(r"\bpython[0-9.]*(?:\.exe)?\s+-c\s", re.I)),
    ("cmd-sed-i", re.compile(r"\bsed\b[^\n|;&]*\s-[a-zA-Z]*i\b|\bperl\s+-[a-zA-Z]*i")),
    ("cmd-redirect-src", re.compile(r">{1,2}\s*['\"]?[^\s|;&<>]+\.(?:h|cpp|cs|py|md|ini|json|ps1|uplugin"
                                    r"|uproject)\b", re.I)),
    ("cmd-here-string", re.compile(r"@['\"]\s*\r?\n")),
    ("cmd-set-content", re.compile(r"\b(?:Set-Content|Add-Content|Out-File|WriteAllText|WriteAllLines"
                                   r"|WriteAllBytes)\b", re.I)),
    ("cmd-unix2dos", re.compile(r"\b(?:unix2dos|dos2unix)\b", re.I)),
    ("cmd-git-checkout-file", re.compile(r"git (?:checkout|restore)\s+(?:--\s+)?\S+\.\w+", re.I)),
)

FILE_ERRORS: tuple[tuple[str, re.Pattern], ...] = (
    ("not-found", re.compile(r"String to replace not found", re.I)),
    ("multiple-matches", re.compile(r"Found \d+ matches of the string to replace", re.I)),
    ("not-read-yet", re.compile(r"has not been read yet|Read it first", re.I)),
    ("modified-since-read", re.compile(r"modified since read|has been (?:unexpectedly )?modified", re.I)),
    ("same-strings", re.compile(r"No changes to make|old_string and new_string are (?:exactly )?the same",
                                re.I)),
    ("too-many-tokens", re.compile(r"exceeds maximum allowed tokens|too large|exceeds maximum allowed size",
                                   re.I)),
    ("file-missing", re.compile(r"does not exist|ENOENT|no such file", re.I)),
    ("is-directory", re.compile(r"EISDIR|is a directory", re.I)),
    ("binary", re.compile(r"binary", re.I)),
    ("permission", re.compile(r"permission|denied|EPERM|EACCES|EBUSY|read-only", re.I)),
    ("user-rejected", re.compile(r"user doesn't want|rejected|The user (?:denied|declined)|was interrupted"
                                 r"|Request interrupted", re.I)),
    ("hook-blocked", re.compile(r"hook", re.I)),
    ("invalid-input", re.compile(r"InputValidationError|invalid|required parameter|must be", re.I)),
    ("notebook", re.compile(r"notebook", re.I)),
)


def labels(tool: str, command: str, result: str, failed: bool) -> tuple[str, ...]:
    """The labels of one recorded call. A file tool call has one when it failed, and none when it ran."""
    if tool in SHELLS:
        return (tuple(name for name, rule in SHELL_RESULT if rule.search(result))
                + tuple(name for name, rule in SHELL_COMMAND if rule.search(command)))
    if failed or "<tool_use_error>" in result:
        return (next((name for name, rule in FILE_ERRORS if rule.search(result)), "other"),)
    return ()
