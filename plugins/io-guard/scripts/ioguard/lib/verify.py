"""The verify commands a user names per file extension, and the command for one written file.

The value is a JSON object. A key that starts with a dot is an extension, and its value is a command: a
list of strings, the program first, with {file} where the file's path goes. Any other key is the absolute
root of one project, and its value is an object of extensions to commands for that project only. A project's
own command for an extension wins over the top-level one. Only the user's config.json may hold this key
(D24), because io-guard starts each command.
"""
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ioguard.lib import paths
from ioguard.lib.platform import Platform

PLACEHOLDER = "{file}"
EXAMPLE = '{".py": ["python", "-m", "py_compile", "{file}"]}'


def command_problem(extension: str, command: Any) -> str | None:
    if not extension.startswith(".") or len(extension) < 2:
        return f"{extension!r} is not a file extension such as .py."
    if (not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command)
            or not any(PLACEHOLDER in part for part in command)):
        return (f"The command for {extension} must be a list of strings, the program first, with "
                f"{PLACEHOLDER} where the file's path goes, such as {EXAMPLE}.")
    return None


def shape_problem(value: Mapping[str, Any]) -> str | None:
    """What is wrong with a verify value, as one sentence, or None."""
    for key, entry in value.items():
        if key.startswith("."):
            problem = command_problem(key, entry)
        elif not Path(key).is_absolute():
            problem = f"{key!r} is neither a file extension such as .py nor an absolute project folder."
        elif not isinstance(entry, Mapping):
            problem = f"The entry for the project {key} must be an object of extensions to commands."
        else:
            problem = next(filter(None, (command_problem(extension, command)
                                         for extension, command in entry.items())), None)
        if problem:
            return problem
    return None


def command_for(value: Mapping[str, Any], path: Path, platform: Platform) -> tuple[str, ...] | None:
    """The command to run on the file at path, with {file} filled in, or None when none is named."""
    extension = path.suffix.lower()
    roots = {paths.normalise(key, path.parent, platform): key for key in value if not key.startswith(".")}
    project = paths.inside(path, roots, platform)
    own = {} if project is None else {name.lower(): command
                                      for name, command in value[roots[project]].items()}
    top = {name.lower(): command for name, command in value.items() if name.startswith(".")}
    command = own.get(extension) or top.get(extension)
    if command is None:
        return None
    return tuple(part.replace(PLACEHOLDER, str(path)) for part in command)
