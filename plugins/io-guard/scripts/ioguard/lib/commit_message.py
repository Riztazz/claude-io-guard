"""Where a git commit command takes its message from, and what in a message a commit policy forbids.

git reads its own options before the subcommand, so -C, -c, --git-dir and --work-tree each take a value
there. After commit, -m and --message give the message, once or more, and -F and --file name a file, - for
stdin. A cluster of short options such as -am ends in m, which takes the next word, and -mtext takes the
rest of its own word. Words arrive unquoted, as lib.shell and lib.pwsh give them.
"""
from collections.abc import Sequence
from dataclasses import dataclass

GIT_VALUE_OPTIONS = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"})
COMMIT_VALUE_SHORT = frozenset("mFCctS")     # short options of git commit whose value may follow


@dataclass(frozen=True)
class Sources:
    texts: tuple[str, ...]          # each -m value as written
    files: tuple[str, ...]          # each -F path, or - for stdin


@dataclass(frozen=True)
class Problem:
    what: str                       # the forbidden text, or the non-ASCII character as U+XXXX
    line: int                       # the message line it is on, counted from 1


def subcommand(words: Sequence[str]) -> int | None:
    """The index of git's subcommand in words, or None when the words do not run git or name none."""
    if not words or words[0].replace("\\", "/").rsplit("/", 1)[-1].lower() not in ("git", "git.exe"):
        return None
    at = 1
    while at < len(words) and words[at].startswith("-"):
        at += 2 if words[at] in GIT_VALUE_OPTIONS else 1
    return at if at < len(words) else None


def sources(words: Sequence[str]) -> Sources | None:
    """Where a git commit takes its message from, or None when the words are not a git commit."""
    at = subcommand(words)
    if at is None or words[at] != "commit":
        return None
    texts, files = [], []
    rest = list(words[at + 1:])
    index = 0
    while index < len(rest):
        word = rest[index]
        index += 1
        for name, found in (("--message", texts), ("--file", files)):
            if word == name and index < len(rest):
                found.append(rest[index])
                index += 1
            elif word.startswith(name + "="):
                found.append(word[len(name) + 1:])
        if not word.startswith("-") or word.startswith("--") or word == "-":
            continue
        for position, letter in enumerate(word[1:], 1):
            if letter not in COMMIT_VALUE_SHORT:
                continue
            value = word[position + 1:]
            if not value and letter != "S" and index < len(rest):
                value = rest[index]
                index += 1
            if letter == "m":
                texts.append(value)
            elif letter == "F":
                files.append(value)
            break
    return Sources(tuple(texts), tuple(files))


def problems(message: str, forbid: Sequence[str], ascii_only: bool) -> tuple[Problem, ...]:
    """Each forbidden text the message holds, without regard to case, and with ascii_only its first non-ASCII
    character, each with the line it is on."""
    lines = message.splitlines() or [""]
    found = []
    for text in forbid:
        where = next((number for number, line in enumerate(lines, 1) if text.lower() in line.lower()), None)
        if text and where is not None:
            found.append(Problem(text, where))
    wide = ((number, char) for number, line in enumerate(lines, 1) for char in line if ord(char) > 127)
    first = next(wide, None) if ascii_only else None
    if first is not None:
        found.append(Problem(f"U+{ord(first[1]):04X}", first[0]))
    return tuple(found)
