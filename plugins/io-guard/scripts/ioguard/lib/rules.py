"""Claude Code's Bash and PowerShell permission rules, read from its settings files and matched against an
argument list before io.run runs it.

Settings cannot match an MCP tool's arguments, so a rule such as Bash(git push *) never reaches io.run on its
own (D14). io-guard reads the deny and ask rules of every settings file Claude Code reads: the user's, the
project's, the project's local file and the managed one, where allowManagedPermissionRulesOnly leaves the
managed rules alone. It matches them as the permissions docs describe. A * stands for any text, a trailing
space and * also match the bare command, a trailing :* is the same as a trailing space and *, and a bare
Bash or Bash(*) matches every command. A Bash rule compares case as written, and a PowerShell rule ignores
case, but io-guard does not map PowerShell aliases to their cmdlets as Claude Code does. The wrappers Claude
Code strips first, such as timeout 30, nohup or a bare xargs, and any leading NAME=value, are stripped here
too. A rule meets the command with its program as written or by its bare name, so C:/Git/cmd/git.exe push
meets Bash(git push *), which Claude Code's own matching would not. Deny outranks ask. Allow rules are left
to Claude Code, which prompts for io.run as for any MCP tool.
"""
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath

from ioguard.lib.platform import Platform

RULE = re.compile(r"^(Bash|PowerShell)(?:\((.*)\))?$", re.S)
PARAMETER = re.compile(r"^\s*(?:command|run_in_background|dangerouslyDisableSandbox)\s*:")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PLAIN_WRAPPERS = frozenset({"time", "nohup", "builtin", "noglob"})
PROGRAM_SUFFIXES = (".exe", ".cmd", ".bat", ".com")
MANAGED = {"win32": Path("C:/Program Files/ClaudeCode/managed-settings.json"),
           "darwin": Path("/Library/Application Support/ClaudeCode/managed-settings.json")}


@dataclass(frozen=True)
class Rule:
    tool: str                        # "Bash" or "PowerShell"
    pattern: str | None              # None for a bare rule, which matches every command
    text: str                        # as the settings file writes it, such as Bash(git push *)
    source: Path


@dataclass(frozen=True)
class Rules:
    deny: tuple[Rule, ...] = ()
    ask: tuple[Rule, ...] = ()
    managed_only: bool = False       # the managed file set allowManagedPermissionRulesOnly


@dataclass(frozen=True)
class RuleMatch:
    decision: str                    # "deny", "ask" or "none"
    rule: Rule | None
    command: str                     # the command text the rule met, or the argv as text


def settings_files(env: Mapping[str, str], project: Path, platform: Platform) -> tuple[Path, ...]:
    """The settings files Claude Code reads permission rules from, the managed one first."""
    home = env.get("USERPROFILE") or env.get("HOME") or str(Path.home())
    config = Path(env["CLAUDE_CONFIG_DIR"]) if env.get("CLAUDE_CONFIG_DIR") else Path(home) / ".claude"
    managed = (MANAGED[platform.os],) if platform.os in MANAGED else ()
    return (*managed, config / "settings.json", project / ".claude" / "settings.json",
            project / ".claude" / "settings.local.json")


def load(files: Sequence[Path], read: Callable[[Path], bytes | None]) -> Rules:
    """The rules of every file read returns bytes for, in settings_files' order, the managed file first."""
    managed = set(MANAGED.values())
    return merged(rules_in(data, path, path in managed) for path in files if (data := read(path)) is not None)


def rules_in(data: bytes, source: Path, managed: bool = False) -> Rules:
    """The Bash and PowerShell deny and ask rules of one settings file. A file that is not JSON holds none,
    and only the managed file can make its rules the only ones."""
    try:
        raw = json.loads(data)
    except ValueError:
        return Rules()
    permissions = raw.get("permissions") if isinstance(raw, dict) else None
    if not isinstance(permissions, dict):
        return Rules()

    def listed(kind: str) -> tuple[Rule, ...]:
        found = permissions.get(kind)
        if not isinstance(found, list):
            return ()
        return tuple(rule for text in found if isinstance(text, str) and (rule := parsed(text, source)))
    return Rules(listed("deny"), listed("ask"),
                 managed and permissions.get("allowManagedPermissionRulesOnly") is True)


def parsed(text: str, source: Path) -> Rule | None:
    """A Bash or PowerShell rule, or None for another tool's rule or a rule on a Bash parameter."""
    match = RULE.match(text.strip())
    if match is None or (match[2] is not None and PARAMETER.match(match[2])):
        return None
    pattern = match[2]
    return Rule(match[1], None if pattern is None or pattern.strip() == "*" else pattern, text, source)


def merged(found: Iterable[Rules]) -> Rules:
    """Every file's rules together, or only the first file's when it is managed and says so."""
    found = list(found)
    if found and found[0].managed_only:
        return found[0]
    return Rules(tuple(rule for rules in found for rule in rules.deny),
                 tuple(rule for rules in found for rule in rules.ask))


def unwrapped(words: Sequence[str]) -> list[str]:
    """words without the leading assignments and wrappers Claude Code strips before it matches a rule."""
    words = list(words)
    while words:
        head = words[0]
        if ASSIGNMENT.match(head) or head in PLAIN_WRAPPERS or (head == "command" and words[1:2] != ["-v"]):
            words = words[1:]
        elif head in ("timeout", "nice", "stdbuf"):
            rest = words[1:]
            while rest and rest[0].startswith("-"):
                rest = rest[2:] if rest[0] in ("-s", "-k", "-n", "-i", "-o", "-e") else rest[1:]
            words = rest[1:] if head == "timeout" else rest
        elif head == "xargs" and len(words) > 1 and not words[1].startswith("-"):
            words = words[1:]
        else:
            break
    return words


def command_text(words: Sequence[str]) -> str:
    """The words as one command line, a word with a space or a quote in single quotes."""
    return " ".join(word if word and not re.search(r"[\s'\"]", word) else "'" + word.replace("'", "'\\''")
                    + "'" for word in words)


def matches(rule: Rule, command: str) -> bool:
    if rule.pattern is None:
        return True
    pattern = rule.pattern[:-2] + " *" if rule.pattern.endswith(":*") else rule.pattern
    if pattern.endswith(" *") and pattern.count("*") == 1:
        regex = re.escape(pattern[:-2]) + "(?: .*)?"
    else:
        regex = ".*".join(re.escape(part) for part in pattern.split("*"))
    flags = re.S | (re.I if rule.tool == "PowerShell" else 0)
    return re.fullmatch(regex, command, flags) is not None


def named(words: Sequence[str]) -> list[str]:
    """words with the program by its bare name, such as git for C:/Git/cmd/git.exe."""
    if not words:
        return []
    bare = PurePath(words[0].replace("\\", "/")).name
    for suffix in PROGRAM_SUFFIXES:
        bare = bare.removesuffix(suffix).removesuffix(suffix.upper())
    return [bare, *words[1:]]


def match_argv(rules: Rules, argv: Sequence[str]) -> RuleMatch:
    """The first deny rule, then the first ask rule, that meets argv, with its program as written or by its
    bare name."""
    words = unwrapped(argv)
    texts = [command_text(words)]
    if words:
        texts.append(command_text(named(words)))
    for decision, listed in (("deny", rules.deny), ("ask", rules.ask)):
        for rule in listed:
            met = next((text for text in texts if matches(rule, text)), None)
            if met is not None:
                return RuleMatch(decision, rule, met)
    return RuleMatch("none", None, texts[0])
