"""The commands a user names per file extension: the verify command io-guard runs on a file after each write,
and the format command io.format runs over a file's changed lines.

The value is a JSON object. A key that starts with a dot is an extension, and its value is a command: a
list of strings, the program first. Any other key is the absolute root of one project, and its value is an
object of extensions to commands for that project only. A project's own command for an extension wins over
the top-level one. {file} in an argument becomes the file's path, and an argument that holds {first} and
{last} repeats once per line range. Only the user's config.json may hold either key (D24), because io-guard
starts each command.
"""
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ioguard.lib import paths
from ioguard.lib.platform import Platform

FILE = "{file}"
FIRST = "{first}"
LAST = "{last}"
CLANG_FORMAT = ["clang-format", "--style=file", "--fallback-style=none", f"--assume-filename={FILE}",
                f"--lines={FIRST}:{LAST}"]
C_FAMILY = (".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx", ".inl", ".ipp")
FORMAT_DEFAULT = {extension: CLANG_FORMAT for extension in C_FAMILY}


@dataclass(frozen=True)
class Kind:
    """What one key's commands must hold: some argument holds every mark."""
    marks: tuple[str, ...]
    need: str
    example: str


VERIFY = Kind((FILE,), f"{FILE} where the file's path goes",
              '{".py": ["python", "-m", "py_compile", "{file}"]}')
FORMAT = Kind((FIRST, LAST), f"{FIRST} and {LAST} in one argument, which repeats for each line range",
              '{".py": ["black", "-q", "--line-ranges={first}-{last}", "-"]}')


def command_problem(kind: Kind, extension: str, command: Any) -> str | None:
    if not extension.startswith(".") or len(extension) < 2:
        return f"{extension!r} is not a file extension such as .py."
    if (not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command)
            or not any(all(mark in part for mark in kind.marks) for part in command)):
        return (f"The command for {extension} must be a list of strings, the program first, with "
                f"{kind.need}, such as {kind.example}.")
    return None


def shape_problem(kind: Kind, value: Mapping[str, Any]) -> str | None:
    """What is wrong with a value of kind, as one sentence, or None."""
    for key, entry in value.items():
        if key.startswith("."):
            problem = command_problem(kind, key, entry)
        elif not Path(key).is_absolute():
            problem = f"{key!r} is neither a file extension such as .py nor an absolute project folder."
        elif not isinstance(entry, Mapping):
            problem = f"The entry for the project {key} must be an object of extensions to commands."
        else:
            problem = next(filter(None, (command_problem(kind, extension, command)
                                         for extension, command in entry.items())), None)
        if problem:
            return problem
    return None


def verify_problem(value: Mapping[str, Any]) -> str | None:
    return shape_problem(VERIFY, value)


def format_problem(value: Mapping[str, Any]) -> str | None:
    return shape_problem(FORMAT, value)


def command_for(value: Mapping[str, Any], path: Path, platform: Platform) -> tuple[str, ...] | None:
    """The command named for the file at path, as the user wrote it, or None when none is named."""
    extension = path.suffix.lower()
    roots = {paths.normalise(key, path.parent, platform): key for key in value if not key.startswith(".")}
    project = paths.inside(path, roots, platform)
    own = {} if project is None else {name.lower(): command
                                      for name, command in value[roots[project]].items()}
    top = {name.lower(): command for name, command in value.items() if name.startswith(".")}
    command = own.get(extension) or top.get(extension)
    return None if command is None else tuple(command)


def filled(command: Sequence[str], path: Path, ranges: Sequence[tuple[int, int]] = ()) -> tuple[str, ...]:
    """command with {file} as path, and each argument that holds {first} or {last} once per range."""
    argv = []
    for part in command:
        part = part.replace(FILE, str(path))
        if FIRST in part or LAST in part:
            argv.extend(part.replace(FIRST, str(first)).replace(LAST, str(last)) for first, last in ranges)
        else:
            argv.append(part)
    return tuple(argv)
