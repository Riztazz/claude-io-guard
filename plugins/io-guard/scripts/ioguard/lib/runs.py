"""What an io.run call runs: its argv as given, or the interpreter for its code body's language and the file
the body is written to. The PreToolUse hook on the call and the tool itself both read the call through here,
so a rule the hook asked about is the rule the tool finds.
"""
import hashlib
import os
from collections.abc import Mapping
from typing import Any

from ioguard.lib import proc
from ioguard.lib.context import Probe
from ioguard.lib.platform import Platform
from ioguard.lib.rules import command_text

SUFFIXES = {"python": ".py", "bash": ".sh", "powershell": ".ps1", "node": ".js"}
BODY = "io-run-body"


def interpreter(lang: str, probe: Probe, platform: Platform) -> tuple[str, ...] | None:
    """The argv that runs a file of lang, before the file's path, or None when this machine has no
    interpreter for it. PowerShell is pwsh, or Windows PowerShell where pwsh is missing."""
    match lang:
        case "python":
            return (probe.python.path,)
        case "bash":
            found = probe.bash.path if probe.bash else proc.on_path("bash", os.environ)
            return None if found is None else (found,)
        case "powershell":
            found = probe.pwsh.path if probe.pwsh else proc.on_path("pwsh", os.environ)
            found = found or (proc.on_path("powershell", os.environ) if platform.windows else None)
            return None if found is None else (found, "-NoProfile", "-NonInteractive", "-File")
        case "node":
            found = proc.on_path("node", os.environ)
            return None if found is None else (found,)
    return None


def argv_of(given: Mapping[str, Any], probe: Probe, platform: Platform, body: str | None = None
            ) -> tuple[str, ...] | None:
    """The argv a call runs: its argv, or its body's interpreter and the body's file, named body or a
    stand-in name before the file exists. None for a language with no interpreter here."""
    if given.get("argv"):
        return tuple(str(word) for word in given["argv"])
    lang = str(given.get("lang") or "")
    found = interpreter(lang, probe, platform)
    if found is None:
        return None
    return (*found, body or BODY + SUFFIXES.get(lang, ""))


def key(given: Mapping[str, Any]) -> str:
    """One string per command a call runs, which the hook records when it asks and the tool looks up."""
    if given.get("argv"):
        return "argv " + command_text([str(word) for word in given["argv"]])
    code = str(given.get("code") or "").encode("utf-8")
    return f"code {given.get('lang')} {hashlib.sha256(code).hexdigest()}"
