"""The .editorconfig properties that apply to one file, as the EditorConfig format defines them.

The files are read from the file's folder upward, and the walk stops at one that says root = true. A nearer
file overrides a farther one, and a later section overrides an earlier one in the same file. A glob with no
slash matches the file's name in any folder below the .editorconfig, and one with a slash matches the path
from that folder. Property names and the values io-guard reads are lowercase, as the format asks.
"""
import re
from collections.abc import Callable
from pathlib import Path

SECTION = re.compile(r"^\s*\[(.*)\]\s*$")
PROPERTY = re.compile(r"^\s*([^=:#;]+?)\s*[=:]\s*(.*?)\s*$")
ALTERNATIVES = 256                  # the globs one {a,b} set stands for at most, however deep the braces


def parse(text: str) -> tuple[bool, list[tuple[str, dict[str, str]]]]:
    """Whether the file says root = true, and its sections in order, each a glob and its properties."""
    root, sections = False, []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", ";")):
            continue
        if header := SECTION.match(line):
            sections.append((header[1], {}))
        elif found := PROPERTY.match(line):
            key, value = found[1].lower(), found[2]
            if sections:
                sections[-1][1][key] = value.lower() if key != "indent_size" else value
            elif key == "root":
                root = value.lower() == "true"
    return root, sections


def alternatives(glob: str) -> list[str]:
    """The globs {a,b} stands for, braces nested included, at most ALTERNATIVES of them. A { with no } is a
    plain character, and so is one with no comma inside, whose braces go."""
    opening, depth = -1, 0
    for at, char in enumerate(glob):
        if char == "{":
            opening, depth = (at, 1) if depth == 0 else (opening, depth + 1)
        elif char == "}" and depth:
            depth -= 1
            if depth == 0:
                parts, level, start = [], 0, opening + 1
                for inner in range(opening + 1, at):
                    level += {"{": 1, "}": -1}.get(glob[inner], 0)
                    if glob[inner] == "," and level == 0:
                        parts.append(glob[start:inner])
                        start = inner + 1
                parts.append(glob[start:at])
                found: list[str] = []
                for part in parts:
                    found += alternatives(glob[:opening] + part + glob[at + 1:])
                    if len(found) >= ALTERNATIVES:
                        return found[:ALTERNATIVES]
                return found
    return [glob]


def tokens(glob: str) -> list[tuple[str, Callable[[str], bool] | None]]:
    """A glob with no braces as steps: one character that meets a test, * within a folder, ** across folders,
    and **/ for no folder or any folders."""
    found: list[tuple[str, Callable[[str], bool] | None]] = []
    at = 0
    while at < len(glob):
        char = glob[at]
        if glob.startswith("**/", at):
            found.append(("dirs", None))
            at += 3
            continue
        if glob.startswith("**", at):
            found.append(("any", None))
            at += 2
            continue
        if char == "*":
            found.append(("star", None))
        elif char == "?":
            found.append(("one", lambda given: given != "/"))
        elif char == "[" and (close := glob.find("]", at + 1)) >= 0:
            found.append(("one", in_class(glob[at + 1:close])))
            at = close
        else:
            found.append(("one", lambda given, wanted=char: given == wanted))
        at += 1
    return found


def in_class(inner: str) -> Callable[[str], bool]:
    """The test for [inner]: its characters and a-z ranges, all turned round by a leading !. A range whose
    ends are the wrong way round holds nothing."""
    negated, body = inner.startswith("!"), inner[1:] if inner.startswith("!") else inner
    singles, ranges, at = set(), [], 0
    while at < len(body):
        if at + 2 < len(body) and body[at + 1] == "-":
            ranges.append((body[at], body[at + 2]))
            at += 3
        else:
            singles.add(body[at])
            at += 1
    return lambda given: (given in singles or any(low <= given <= high for low, high in ranges)) != negated


def covers(steps: list[tuple[str, Callable[[str], bool] | None]], text: str) -> bool:
    """Whether the steps match all of text. Each step marks the offsets it can end at, so the work is the
    steps times the text's length, however many stars the glob holds."""
    reach = bytearray(len(text) + 1)
    reach[0] = 1
    for kind, test in steps:
        after = bytearray(len(text) + 1)
        if kind == "one":
            for at in range(len(text)):
                if reach[at] and test(text[at]):
                    after[at + 1] = 1
        elif kind == "any":
            first = reach.find(1)
            after[first:] = b"\x01" * (len(text) + 1 - first)
        else:
            carry = False
            for at in range(len(text) + 1):
                if kind == "dirs":
                    after[at] = reach[at] or (carry and text[at - 1] == "/")
                    carry = carry or bool(reach[at])
                else:
                    carry = carry or bool(reach[at])
                    after[at] = carry
                    carry = carry and (at == len(text) or text[at] != "/")
        if not any(after):
            return False
        reach = after
    return bool(reach[len(text)])


def matches(glob: str, relative: str) -> bool:
    """Whether glob, from an .editorconfig, covers the file at relative, its path from that file's folder."""
    target, glob = (relative, glob.lstrip("/")) if "/" in glob else (relative.rsplit("/", 1)[-1], glob)
    return any(covers(tokens(each), target) for each in alternatives(glob))


def properties(path: Path, read: Callable[[Path], str | None]) -> dict[str, str]:
    """The properties for the file at path. read returns an .editorconfig's text, or None for no file."""
    found: list[tuple[Path, list[tuple[str, dict[str, str]]]]] = []
    for folder in path.parents:
        text = read(folder / ".editorconfig")
        if text is None:
            continue
        root, sections = parse(text)
        found.append((folder, sections))
        if root:
            break
    merged: dict[str, str] = {}
    for folder, sections in reversed(found):
        relative = path.relative_to(folder).as_posix()
        for glob, values in sections:
            if matches(glob, relative):
                merged.update(values)
    return merged
