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

A shell given a command string, such as bash -c "git push", pwsh -Command "git push" or an -EncodedCommand,
runs the commands in that string, so match_command matches each of them too, through nested shells up to
NESTED deep. The string is read as the shell reads it: a backslash before a newline joins the lines, (( ))
is arithmetic, and a PowerShell script block runs its own commands. A string io-guard cannot read, such as
one with a command substitution, an eval or a heredoc with no end, a cmd /c line or an interpreter's code
string such as python -c, gives the decision "unread" when it names the program of a
deny or ask rule as a word, such as git for Bash(git push *), and the caller weighs it. Code can build a
program's name from parts, so a string that names none can still run one.
"""
import base64
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath

from ioguard.lib import pwsh, shell
from ioguard.lib.platform import Platform

RULE = re.compile(r"^(Bash|PowerShell)(?:\((.*)\))?$", re.S)
PARAMETER = re.compile(r"^\s*(?:command|run_in_background|dangerouslyDisableSandbox)\s*:")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PLAIN_WRAPPERS = frozenset({"time", "nohup", "builtin", "noglob"})
PROGRAM_SUFFIXES = (".exe", ".cmd", ".bat", ".com")
SHELLS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "mksh", "fish"})
SHELL_C = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")
SHELL_VALUED = frozenset({"-o", "+o", "-O", "+O", "--rcfile", "--init-file"})
POWERSHELLS = frozenset({"pwsh", "powershell"})
PWSH_VALUED = frozenset({"-executionpolicy", "-ep", "-ex", "-workingdirectory", "-wd", "-configurationname",
                         "-outputformat", "-of", "-inputformat", "-if", "-windowstyle", "-w", "-version",
                         "-v",
                         "-settingsfile", "-custompipename", "-psconsolefile"})
CODE_FLAGS = {"python": ("-c",), "py": ("-c",), "node": ("-e", "-p", "--eval", "--print"),
              "perl": ("-e", "-E"), "ruby": ("-e",), "php": ("-r",), "deno": ("eval",),
              "bun": ("-e", "--eval")}
CODE_VALUED = frozenset({"-X", "-W", "-r", "--require", "--import", "--loader"})
UNREAD_BASH =("$(", "`", "<(", ">(")
ARITHMETIC = re.compile(r"\(\(.*\)\)", re.S)     # bash's (( ... )), which runs no command
PWSH_ASSIGNS = frozenset({"=", "+=", "-=", "*=", "/=", "%=", "??="})
PWSH_ASSIGNMENT = re.compile(r"^\$[\w:]+(?:\+|-|\*|/|%|\?\?)?=(.*)$", re.S)   # $x=value, written as one word
READS_TEXT = frozenset({"eval", "source", ".", "iex", "invoke-expression", "invoke-command"})
NESTED = 4
BLOCKS = 16                                      # script blocks inside script blocks read before unread
MANAGED = {"win32":Path("C:/Program Files/ClaudeCode/managed-settings.json"),
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
    decision: str                    # "deny", "ask", "unread" or "none"
    rule: Rule | None                # None for "unread", and for an ask the caller makes without a rule
    command: str                     # the command text the rule met, the argv as text, or what is unread


@dataclass(frozen=True)
class Wrapped:
    what: str                        # how the string is given, such as bash -c or python -c
    text: str | None                 # the command string a shell runs, None when io-guard cannot read it
    dialect: str                     # "bash" or "powershell", "" for text io-guard cannot read
    raw: str = ""                    # the string as given, which rule_named searches


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
    """The Bash and PowerShell deny and ask rules of one settings file. A file that is not JSON, or JSON
    nested or numbered past what Python parses, holds none, and only the managed file can make its rules the
    only ones."""
    try:
        raw = json.loads(data)
    except (ValueError, RecursionError):
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


def wrapped(words: Sequence[str]) -> Wrapped | None:
    """The command string a shell or an interpreter among words is given to run, or None when words run a
    program or a script file. words are already unwrapped."""
    if not words:
        return None
    program = re.sub(r"(?<=^python)[\d.]+$", "", named(words)[0].lower())
    rest = list(words[1:])
    if program in SHELLS:
        while rest and (rest[0].startswith(("-", "+")) and rest[0] != "--"):
            if SHELL_C.match(rest[0]):
                text = rest[1] if len(rest) > 1 else ""
                return Wrapped(f"{program} -c", text, "bash", text)
            rest = rest[2:] if rest[0] in SHELL_VALUED else rest[1:]
        return None
    if program in POWERSHELLS:
        while rest and rest[0].startswith("-"):
            flag = rest[0].lower()
            if flag in ("-c", "-command") or (len(flag) >= 4 and "-command".startswith(flag)):
                text = " ".join(rest[1:])
                return Wrapped(f"{program} -Command", text, "powershell", text)
            if flag in ("-e", "-ec", "-en") or (len(flag) >= 4 and "-encodedcommand".startswith(flag)):
                return encoded(program, rest[1] if len(rest) > 1 else "")
            if flag in ("-f", "-file") or (len(flag) >= 3 and "-file".startswith(flag)):
                return None
            rest = rest[2:] if flag in PWSH_VALUED else rest[1:]
        text = " ".join(rest)
        return Wrapped(f"{program} with a command", text, "powershell", text) \
            if rest and program == "powershell" else None
    if program == "cmd":
        at = next((index for index, word in enumerate(rest) if word.lower() in ("/c", "/k")), None)
        return None if at is None else Wrapped("cmd /c", None, "", " ".join(rest[at + 1:]))
    flags = CODE_FLAGS.get(program, ())
    while rest and rest[0].startswith("-") and rest[0] not in flags:
        rest = rest[2:] if rest[0] in CODE_VALUED else rest[1:]
    if not rest or rest[0] not in flags:
        return None
    return Wrapped(f"{program} {rest[0]}", None, "", " ".join(rest[1:]))


def encoded(program: str, given: str) -> Wrapped:
    """A PowerShell -EncodedCommand, decoded from base64 UTF-16LE to the command it runs, or unread when it
    does not decode."""
    try:
        text = base64.b64decode(given, validate=True).decode("utf-16-le")
    except (ValueError, UnicodeDecodeError):
        return Wrapped(f"{program} -EncodedCommand", None, "", given)
    return Wrapped(f"{program} -EncodedCommand", text, "powershell", text)


def rule_named(rules: Rules, text: str) -> Rule | None:
    """The first deny rule, then the first ask rule, whose program text names as a word, such as git for
    Bash(git push *). A bare rule, or one whose program is a wildcard, names every text."""
    for rule in (*rules.deny, *rules.ask):
        program = (rule.pattern or "").split(" ")[0].removesuffix(":*")
        if not program or "*" in program:
            return rule
        if re.search(rf"(?<![\w.-]){re.escape(program)}(?![\w-])", text, re.I):
            return rule
    return None


def inner(found: Wrapped) -> list[list[str]] | None:
    """The simple commands the string a shell is given runs, or None when io-guard cannot read all of them:
    a command substitution, a process substitution, eval or source, a call through a variable, or a heredoc
    whose end io-guard does not find, which bash may find elsewhere."""
    if found.text is None:
        return None
    if found.dialect == "bash":
        if any(mark in found.text for mark in UNREAD_BASH):
            return None
        scanned = shell.scan(found.text)
        if scanned.too_deep or any(not heredoc.terminated for heredoc in scanned.heredocs):
            return None
        parts = [list(simple.words) for simple in shell.commands(found.text)
                 if not (simple.words and ARITHMETIC.fullmatch(simple.words[0]))]
    else:
        if "$(" in found.text:
            return None
        parts = powershell_parts(found.text, 0)
        if parts is None:
            return None
    if any(part and (part[0].lower() in READS_TEXT or part[0].startswith(("$", "("))) for part in parts):
        return None
    return parts


def powershell_parts(text: str, depth: int) -> list[list[str]] | None:
    """The simple commands of a PowerShell string, with those of each script block inside it, or None past
    BLOCKS deep."""
    if depth > BLOCKS:
        return None
    parts = [statement(list(simple.words)) for simple in pwsh.commands(text)]
    for block in pwsh.script_blocks(text):
        inside = powershell_parts(block, depth + 1)
        if inside is None:
            return None
        parts += inside
    return parts


def statement(words: list[str]) -> list[str]:
    """The command a PowerShell statement runs: the right side of an assignment, a call through & or . with
    the operator dropped, and nothing for an expression such as $_.Line. A call through a variable keeps the
    variable first, which inner reads as unread."""
    if words and words[0].startswith("$"):
        joined = PWSH_ASSIGNMENT.match(words[0])
        if joined:
            words = [joined[1], *words[1:]] if joined[1] else words[1:]
        elif words[1:2] and words[1] in PWSH_ASSIGNS:
            words = words[2:]
        else:
            return []
    if words[:1] in (["&"], ["."]) and len(words) > 1:
        words = words[1:]
    return words


def match_command(rules: Rules, argv: Sequence[str], depth: int = 0) -> RuleMatch:
    """match_argv, and each command a shell among argv is given to run, with deny first, then ask, then
    "unread": a string io-guard cannot read that names a rule's program, with that rule."""
    direct = match_argv(rules, argv)
    found = wrapped(unwrapped(argv))
    if direct.decision == "deny" or found is None:
        return direct
    parts = inner(found) if depth < NESTED else None
    if parts is None:
        named_by = rule_named(rules, found.raw)
        met = [direct] + ([RuleMatch("unread", named_by, found.what)] if named_by else [])
    else:
        met = [direct] + [match_command(rules, part, depth + 1) for part in parts if part]
    return next((each for decision in ("deny", "ask", "unread") for each in met if each.decision == decision),
                direct)
