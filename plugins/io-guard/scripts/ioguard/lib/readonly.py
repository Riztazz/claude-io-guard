"""Whether a Bash command can change a file.

It cannot when every program it runs only reads, nothing goes to a file but /dev/null, and bash runs nothing
the words do not show. A $() or a backtick that bash runs, in code, in double quotes or in a heredoc body, is
such a command, since its words hide what it runs. A reader that takes an option to write is a writer with
it: sed with -i or a w or e command, find with -delete or -exec, sort -o, uniq with an output file, and any
program given --output.
"""
import re
from collections.abc import Sequence

from ioguard.lib import commit_message, shell

READERS = ["ls", "cat", "head", "tail", "grep", "egrep", "fgrep", "wc", "echo", "printf", "pwd", "which",
           "cut", "tr", "stat", "file", "du", "df", "date", "cd", "test", "[", "true", "false", "type",
           "basename", "dirname", "realpath", "readlink", "diff", "cmp", "md5sum", "sha1sum", "sha256sum",
           "column", "nl", "jq", "whoami", "uname", "printenv", "sleep", "comm", "od", "hexdump", "strings",
           "seq", "expr", "read", "for", "select", "while", "until", "break", "continue", "exit", "return",
           "export", "local", "set", "unset", "shift", "sed", "find", "sort", "uniq", "git log", "git show",
           "git diff", "git status", "git blame", "git rev-parse", "git ls-files", "git grep", "git describe",
           "git shortlog", "git cat-file", "git rev-list", "git ls-tree", "git check-ignore",
           "git check-attr", "git merge-base", "git name-rev", "git for-each-ref"]
DISCARDED = frozenset({"/dev/null", "nul"})
RUNS_HIDDEN = (shell.NORMAL, shell.DOUBLE, shell.BODY, shell.ARITH)   # where bash runs a $() or a backtick
SED_WRITES = re.compile(r"(?:^|[;{}\n\s])\d*(?:,\d*)?[wWe](?:\s|$)|s(.).*?\1.*?\1[gpIiMm\d]*[we]")
FIND_WRITES = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf",
                         "-fls"})


def runs_hidden(command: str, found: shell.Scan) -> bool:
    """Whether bash runs a $() or a backtick in the command, whose words do not name what it runs."""
    for at, character in enumerate(command):
        if found.states[at] not in RUNS_HIDDEN:
            continue
        if character == "`" or command.startswith("$(", at) and not command.startswith("$((", at):
            return True
    return False


def writes_with(simple: shell.SimpleCommand) -> bool:
    """Whether a reader is told to write: by sed's -i or its w and e commands, find's actions, sort -o, uniq's
    output file, or --output."""
    words, name = simple.words[1:], simple.name
    if any(word.startswith("--output") for word in words):
        return True
    match name:
        case "sed":
            return any(word.startswith(("--in-place", "-i")) or SED_WRITES.search(word) for word in words)
        case "find":
            return not FIND_WRITES.isdisjoint(words)
        case "sort":
            return any(word == "-o" or word.startswith("-") and not word.startswith("--") and "o" in word
                       for word in words)
        case "uniq":
            return len([word for word in words if not word.startswith("-")]) > 1
    return False


def reads(simple: shell.SimpleCommand, readers: Sequence[str]) -> bool:
    """Whether one simple command only reads: an assignment alone, or a reader named in readers, by git's
    subcommand for git, with no redirect to a file and no option that makes it write."""
    if any(redirect.target.lower() not in DISCARDED for redirect in simple.redirects):
        return False
    if not simple.words:
        return True
    at = commit_message.subcommand(simple.words)
    if at is not None:
        named = f"git {simple.words[at]}".lower() in {entry.lower() for entry in readers}
    else:
        named = shell.matching(simple, readers) is not None
    return named and not writes_with(simple)


def only_reads(command: str, readers: Sequence[str]) -> bool:
    """Whether the Bash command can change no file: every simple command in it reads, by readers, and bash
    runs nothing its words hide. A command the scan cannot read to its end can change anything."""
    found = shell.scan(command)
    if found.unterminated or found.too_deep or runs_hidden(command, found):
        return False
    simples = shell.commands(command)
    return bool(simples) and all(reads(simple, readers) for simple in simples)
