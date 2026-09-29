"""Reading a PowerShell command far enough to find what it writes and what it gets wrong: its simple commands,
their words and their file redirects, its code with the strings left out, and the paths it hands to [IO.File]
write calls.

The reader follows PowerShell's quoting: '...' with '' inside, "..." with backtick escapes, the here-strings
@'...'@ and @"..."@, # and <# #> comments. It splits at ; | && || and newlines outside them.
"""
import re

from ioguard.lib.shell import Redirect, SimpleCommand

REDIRECT = re.compile(r"(\d|\*)?(>>?)(&\d)?")
FILE_CALL = re.compile(r"\[(?:System\.)?IO\.File\]::(?:WriteAll\w*|AppendAll\w*|Create|Open\w*)\(\s*"
                       r"(?:(['\"])(?P<path>[^'\"]+)\1"
                       r"|\(\s*(?:Resolve-Path|Convert-Path|Get-Item)\s+(?:-(?:Literal)?Path\s+)?(['\"]?)"
                       r"(?P<resolved>[^'\")\s]+)\3\s*\))", re.I)


def quoted_end(text: str, at: int) -> int:
    """The offset after the string, here-string or comment that starts at at."""
    if text.startswith(("@'", '@"'), at) and text[at + 2:at + 3] in ("\n", "\r"):
        close = re.compile(r"^\s*" + re.escape(text[at + 1]) + "@", re.M).search(text, at + 2)
        return len(text) if close is None else close.end()
    if text.startswith("<#", at):
        close = text.find("#>", at + 2)
        return len(text) if close < 0 else close + 2
    quote = text[at]
    at += 1
    while at < len(text):
        if quote == '"' and text[at] == "`":
            at += 2
            continue
        if text[at] == quote:
            if text[at + 1:at + 2] == quote:
                at += 2
                continue
            return at + 1
        at += 1
    return at


def unquote(word: str) -> str:
    if len(word) >= 2 and word[0] == word[-1] and word[0] in "'\"":
        inner = word[1:-1]
        return inner.replace("''", "'") if word[0] == "'" else re.sub(r"`(.)", r"\1", inner)
    return word


def commands(command: str) -> tuple[SimpleCommand, ...]:
    """The simple commands of a PowerShell command, with their words unquoted and their file redirects."""
    text, parsed, at, start = command, [], 0, 0
    words: list[str] = []
    redirects: list[Redirect] = []

    def finish(end: int) -> None:
        nonlocal words, redirects
        if words or redirects:
            unquoted = tuple(unquote(word) for word in words)
            parsed.append(SimpleCommand(unquoted, tuple(redirects), (), (start, end)))
        words, redirects = [], []

    while at < len(text):
        char = text[at]
        if char == "#" and (at == 0 or text[at - 1] in " \t\n;|("):
            end = text.find("\n", at)
            at = len(text) if end < 0 else end
        elif text.startswith("<#", at):
            at = quoted_end(text, at)
        elif char in ";\n|" or text.startswith("&&", at):
            finish(at)
            at += 2 if text.startswith(("&&", "||"), at) else 1
            start = at
        elif char in " \t\r":
            at += 1
        elif (match := REDIRECT.match(text, at)) and (at == 0 or text[at - 1] in " \t" or text[at] == ">"):
            at = match.end()
            if match[3]:
                continue
            while at < len(text) and text[at] in " \t":
                at += 1
            end = word_at(text, at)
            redirects.append(Redirect(unquote(text[at:end]), match[2] == ">>",
                                      None if match[1] == "*" else int(match[1] or 1)))
            at = end
        else:
            end = word_at(text, at)
            words.append(text[at:end])
            at = end
    finish(len(text))
    return tuple(parsed)


def word_at(text: str, at: int) -> int:
    """The end of the word at at, with strings, here-strings and bracketed parts kept whole."""
    depth = 0
    while at < len(text):
        char = text[at]
        here = text.startswith(("@'", '@"'), at) and text[at + 2:at + 3] in ("\n", "\r")
        if here or char in "'\"":
            at = quoted_end(text, at)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            if depth == 0:
                return at
            depth -= 1
        elif depth == 0 and (char in " \t\r\n;|>" or text.startswith("&&", at)):
            return at
        at += 1
    return at


def blanked(command: str) -> str:
    """The command with each string, here-string and comment turned into spaces, so a search of what is left
    finds only code. Newlines stay, so an offset still points at the same place."""
    out, at = [], 0
    while at < len(command):
        char = command[at]
        here = command.startswith(("@'", '@"'), at) and command[at + 2:at + 3] in ("\n", "\r")
        if here or char in "'\"" or command.startswith("<#", at):
            end = quoted_end(command, at)
        elif char == "#" and (at == 0 or command[at - 1] in " \t\n;|("):
            end = command.find("\n", at)
            end = len(command) if end < 0 else end
        else:
            out.append(char)
            at += 1
            continue
        out.append(re.sub(r"[^\n]", " ", command[at:end]))
        at = end
    return "".join(out)


def script_blocks(command: str) -> tuple[str, ...]:
    """The text inside each outermost { } of the command, outside strings and comments: the script blocks
    of & { }, an if or foreach body, and a ForEach-Object block, each of which runs its own commands."""
    code, found, depth, start = blanked(command), [], 0, 0
    for at, char in enumerate(code):
        if char == "{":
            if depth == 0:
                start = at + 1
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0:
                found.append(command[start:at])
    return tuple(found)


def file_calls(command: str) -> tuple[str, ...]:
    """The literal paths [IO.File] write calls name."""
    return tuple(match["path"] or match["resolved"] for match in FILE_CALL.finditer(command))
