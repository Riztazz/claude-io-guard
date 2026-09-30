"""The program a command word names, such as git for C:\\Git\\cmd\\git.exe.

Every reader of a command's first word takes its program from here, so the shell parser, the permission rules,
the write finder, the commit reader and the telemetry agree on which program a command runs.
"""
import re
from collections.abc import Sequence

PROGRAM_SUFFIXES = (".exe", ".cmd", ".bat", ".com")    # what Windows runs a program from


def program_name(word: str, suffixes: Sequence[str] = (".exe",), fold: bool = True) -> str:
    """The last segment of word on either separator, less the first of suffixes it ends with, matched without
    case. fold gives the name in lower case."""
    name = re.split(r"[\\/]", word)[-1]
    lowered = name.lower()
    ending = next((suffix for suffix in suffixes if lowered.endswith(suffix.lower())), "")
    name = name[:len(name) - len(ending)]
    return name.lower() if fold else name
