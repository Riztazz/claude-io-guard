"""What an io.run call runs: its argv as given, or the interpreter for its code body's language and the file
the body is written to. The PreToolUse hook on the call and the tool itself both read the call through here,
so a rule the hook asked about is the rule the tool finds.
"""
import hashlib
from collections.abc import Mapping
from functools import partial
from pathlib import Path, PureWindowsPath
from typing import Any

from ioguard.lib import proc, rules
from ioguard.lib.context import FsPort, Probe, read_or_none
from ioguard.lib.platform import Platform
from ioguard.lib.rules import RuleVerdict

SUFFIXES = {"python": ".py", "bash": ".sh", "powershell": ".ps1", "node": ".js"}
BODY = "io-run-body"


def interpreter(lang: str, probe: Probe, platform: Platform,
                env: Mapping[str, str]) -> tuple[str, ...] | None:
    """The argv that runs a file of lang, before the file's path, or None when this machine has no
    interpreter for it: the probe's, else the first on env's PATH. PowerShell is pwsh, or Windows PowerShell
    where pwsh is missing."""
    match lang:
        case "python":
            return (probe.python.path,)
        case "bash":
            found = probe.bash.path if probe.bash else proc.on_path("bash", env)
            return None if found is None else (found,)
        case "powershell":
            found = probe.pwsh.path if probe.pwsh else proc.on_path("pwsh", env)
            found = found or (proc.on_path("powershell", env) if platform.windows else None)
            return None if found is None else (found, "-NoProfile", "-NonInteractive", "-File")
        case "node":
            found = proc.on_path("node", env)
            return None if found is None else (found,)
    return None


def git_tools(program: str) -> tuple[str, ...]:
    """The folders Git for Windows' own login shell puts first on PATH, mingw64/bin, usr/local/bin and
    usr/bin, when program is that install's bash, at usr/bin/bash.exe or bin/bash.exe. Empty for any other
    program. bash started straight, as io.run starts it, keeps the Windows PATH as it is, which holds none of
    Git's tools, so tr, diff or sed are not found where the Bash tool finds them."""
    path = PureWindowsPath(program)
    if path.stem.lower() != "bash" or path.parent.name.lower() != "bin":
        return ()
    root = path.parents[2] if path.parents[1].name.lower() == "usr" else path.parents[1]
    if not root.name:
        return ()
    return (str(root / "mingw64" / "bin"), str(root / "usr" / "local" / "bin"), str(root / "usr" / "bin"))


def with_git_tools(env: Mapping[str, str], program: str) -> dict[str, str]:
    """env with git_tools(program) first on its PATH, whatever case its key is spelled in, and MSYSTEM set to
    MINGW64 as the Bash tool sets it, unless env names one. env as it is for any other program."""
    folders = git_tools(program)
    if not folders:
        return dict(env)
    key = next((name for name in env if name.upper() == "PATH"), "PATH")
    rest = [env[key]] if env.get(key) else []
    return {**env, key: ";".join((*folders, *rest)), "MSYSTEM": env.get("MSYSTEM") or "MINGW64"}


def argv_of(given: Mapping[str, Any], probe: Probe, platform: Platform, env: Mapping[str, str],
            body: str | None = None) -> tuple[str, ...] | None:
    """The argv a call runs: its argv, or its body's interpreter and the body's file, named body or a
    stand-in name before the file exists. None for a language with no interpreter here."""
    if given.get("argv"):
        return tuple(str(word) for word in given["argv"])
    lang = str(given.get("lang") or "")
    found = interpreter(lang, probe, platform, env)
    if found is None:
        return None
    return (*found, body or BODY + SUFFIXES.get(lang, ""))


def key(given: Mapping[str, Any]) -> str:
    """One string per command a call runs, which the hook records when it asks and the tool looks up."""
    if given.get("argv"):
        return "argv " + rules.command_text([str(word) for word in given["argv"]])
    code = str(given.get("code") or "").encode("utf-8")
    return f"code {given.get('lang')} {hashlib.sha256(code).hexdigest()}"


def judge(given: Mapping[str, Any], env: Mapping[str, str], fs: FsPort, probe: Probe, platform: Platform,
          project: Path) -> rules.RuleMatch:
    """The deny or ask rule of the settings files Claude Code reads for project that meets the command an
    io.run call runs, or a command inside a shell string it runs, or a match whose decision is none. A code
    body, or a string io-guard cannot read, that names a rule's program asks, whether the rule denies or
    asks, since the rule cannot see what the code does."""
    found = rules.load(rules.settings_files(env, project, platform), partial(read_or_none, fs))
    argv = argv_of(given, probe, platform, env)
    if argv is None:
        return rules.RuleMatch(RuleVerdict.NONE, None, "")
    met = rules.match_command(found, argv)
    if given.get("code") and met.decision is RuleVerdict.NONE:
        named_by = rules.rule_named(found, str(given["code"]))
        if named_by:
            met = rules.RuleMatch(RuleVerdict.UNREAD, named_by, f"a {given.get('lang')} body")
    if met.decision is not RuleVerdict.UNREAD:
        return met
    return rules.RuleMatch(RuleVerdict.ASK, None, f"{met.command}, whose code names the program of the rule "
                                                  f"{met.rule.text} in {met.rule.source.as_posix()}")


def said(found: rules.RuleMatch) -> str:
    """The command and the reason it is denied or asked about, to follow "io.run would run"."""
    if found.rule is None:
        return f"{found.command}, and no rule can read what code does, so the user decides"
    verb = "denies" if found.decision is RuleVerdict.DENY else "asks about"
    return f"{found.command}, which the rule {found.rule.text} in {found.rule.source.as_posix()} {verb}"
