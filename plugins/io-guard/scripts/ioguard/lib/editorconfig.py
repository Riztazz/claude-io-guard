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


def glob_pattern(glob: str) -> re.Pattern:
    """A regex for an EditorConfig glob: * within a folder, ** across folders, ?, [set], [!set], {a,b}."""
    out, at, depth = [], 0, 0
    while at < len(glob):
        char = glob[at]
        if glob.startswith("**/", at):
            out.append("(?:.*/)?")
            at += 3
            continue
        if glob.startswith("**", at):
            out.append(".*")
            at += 2
            continue
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            close = glob.find("]", at + 1)
            if close < 0:
                out.append(re.escape(char))
            else:
                inner = glob[at + 1:close]
                out.append("[" + ("^" + inner[1:] if inner.startswith("!") else inner) + "]")
                at = close
        elif char == "{":
            depth += 1
            out.append("(?:")
        elif char == "}" and depth:
            depth -= 1
            out.append(")")
        elif char == "," and depth:
            out.append("|")
        else:
            out.append(re.escape(char))
        at += 1
    return re.compile("".join(out) + "$")


def matches(glob: str, relative: str) -> bool:
    """Whether glob, from an .editorconfig, covers the file at relative, its path from that file's folder."""
    if "/" not in glob:
        return bool(glob_pattern(glob).match(relative.rsplit("/", 1)[-1]))
    return bool(glob_pattern(glob.lstrip("/")).match(relative))


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
