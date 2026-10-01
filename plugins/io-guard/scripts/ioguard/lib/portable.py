"""What in a bash command needs bash 4 or later, or a GNU tool, and so runs another way, or not at all, under
macOS's /bin/bash 3.2 and its BSD tools.

bash 3.2 has no readarray, no case changes such as ${x,,}, no associative arrays, no |& and &>>, no ;;& in a
case, no globstar, no negative array index and no ${x@Q}. BSD sed reads the word after -i as the backup
suffix, so sed -i 's/a/b/' f takes the script for a suffix. BSD grep has no -P, BSD stat takes -f where GNU
takes -c, BSD date -d does something else, and BSD find, cp, mv, du and head lack -printf, -t, -b and a
negative line count.
"""
import itertools
import re
from collections.abc import Sequence
from dataclasses import dataclass

from ioguard.lib import shell

EXPANDED = (shell.NORMAL, shell.DOUBLE)       # where bash expands a ${...}
OPERATING = (shell.NORMAL,)                    # where bash reads an operator such as |&
BASH4_TEXT = (
    (re.compile(r"\$\{\w+(?:\[[^\]]*\])?(?:,,?|\^\^?)[^}]*\}"), EXPANDED, "the case change",
     "Pipe the value through tr '[:upper:]' '[:lower:]', or tr the other way."),
    (re.compile(r"\|&"), OPERATING, "|&", "Write 2>&1 | instead."),
    (re.compile(r"&>>"), OPERATING, "&>>", "Write >> file 2>&1 instead."),
    (re.compile(r";;&"), OPERATING, ";;& in a case", "Write the cases out one by one."),
    (re.compile(r"\$\{\w+\[-\d+\]\}"), EXPANDED, "a negative array index",
     "Index from the length: ${a[${#a[@]}-1]}."),
    (re.compile(r"\$\{\w+@[QEPAaKk]\}"), EXPANDED, "the ${var@...} transform",
     "Quote the value with printf %q."),
)
BASH4_COMMANDS = {"readarray": "Read the lines in a while IFS= read -r loop.",
                  "mapfile": "Read the lines in a while IFS= read -r loop.",
                  "coproc": "Run the program in the background with its input and output in named pipes."}
GNU_FLAGS = {"grep": ({"-P", "--perl-regexp"}, "Use grep -E, or perl -ne for a Perl pattern."),
             "stat": ({"-c", "--format"}, "Use stat -f with BSD's format letters."),
             "date": ({"-d", "--date"}, "Use date -j -f to read a date."),
             "find": ({"-printf"}, "Use -exec stat -f, or -print and a loop."),
             "cp": ({"-t", "--target-directory"}, "Name the target folder last."),
             "mv": ({"-t", "--target-directory"}, "Name the target folder last."),
             "du": ({"-b", "--bytes"}, "Use du -k, or stat -f %z for one file.")}


@dataclass(frozen=True)
class Unportable:
    what: str          # the construct, as a message names it
    offset: int        # where it starts in the command
    fix: str           # what to write instead


def bash4(command: str, states: bytes, simples: Sequence[shell.SimpleCommand]) -> tuple[Unportable, ...]:
    """The bash 4 or later syntax the command uses where bash reads it, each construct once."""
    found = []
    for pattern, read, what, fix in BASH4_TEXT:
        match = next((match for match in pattern.finditer(command) if states[match.start()] in read), None)
        if match is not None:
            found.append(Unportable(what, match.start(), fix))
    for simple in simples:
        flags = {word for word in simple.words[1:] if word.startswith("-")}
        if simple.name in BASH4_COMMANDS:
            found.append(Unportable(simple.name, simple.span[0], BASH4_COMMANDS[simple.name]))
        elif simple.name in ("declare", "local", "typeset") and any("A" in flag[1:] for flag in flags
                                                                      if not flag.startswith("--")):
            found.append(Unportable(f"{simple.name} -A, an associative array", simple.span[0],
                                    "Keep the keys and values in two indexed arrays, or in a file."))
        elif simple.name == "shopt" and "globstar" in simple.words:
            found.append(Unportable("globstar", simple.span[0], "Use find to walk the folders."))
        elif simple.name == "wait" and "-n" in flags:
            found.append(Unportable("wait -n", simple.span[0], "Wait for each process by its PID."))
    return tuple(sorted(found, key=lambda each: each.offset))


def gnu_only(simples: Sequence[shell.SimpleCommand]) -> tuple[Unportable, ...]:
    """The GNU-only options the command's programs are given, where BSD's read them another way."""
    found = []
    for simple in simples:
        words = simple.words
        following = list(itertools.pairwise([*words, None]))
        if simple.name == "sed":
            long_form = any(word == "--in-place" or word.startswith("--in-place=") for word in words)
            if long_form or any(word == "-i" and after != "" for word, after in following):
                found.append(Unportable("sed -i with no suffix", simple.span[0],
                                        "Write sed -i '' so BSD sed takes the empty suffix."))
        elif simple.name == "head" and any(word == "-n" and (after or "").startswith("-")
                                            for word, after in following):
            found.append(Unportable("head -n with a negative count", simple.span[0],
                                    "Count the lines with wc -l and give head the difference."))
        elif simple.name in GNU_FLAGS:
            flags, fix = GNU_FLAGS[simple.name]
            given = next((word for word in words[1:] if word in flags or word.split("=")[0] in flags), None)
            if given is not None:
                found.append(Unportable(f"{simple.name} {given.split('=')[0]}", simple.span[0], fix))
    return tuple(found)


def major(version: str | None) -> int | None:
    """The major number of a version such as 3.2.57, or None."""
    match = re.match(r"(\d+)", version or "")
    return int(match[1]) if match else None
