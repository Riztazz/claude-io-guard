"""Keep Git Bash from rewriting the arguments and redirects of a command on Windows.

Git Bash turns an argument that starts with a slash into a path under its own install folder when it hands
the argument to a Windows program (PTH-4): /Game/X arrives as C:/Program Files/Git/Game/X, and taskkill's
/PID as C:/Program Files/Git/PID. The check names each such argument in MSYS2_ARG_CONV_EXCL, exported before
the command, and leaves the drive paths and POSIX roots that need the rewrite alone. It writes cmd /c as
cmd //c, because Git Bash turns a lone /c into C:/ and cmd then runs nothing. A redirect to nul writes a real
file named nul in Git Bash, which Windows tools cannot delete (PTH-5), so the check writes /dev/null instead.
Each fix follows the user's rewrite mode (D12).
"""
import re
from collections.abc import Mapping
from typing import Any

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib import paths, shell
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Layer, Severity

POSIX_ROOTS = ["tmp", "usr", "dev", "etc", "home", "bin", "mnt", "proc", "opt", "var", "lib", "sbin",
               "cygdrive"]
MSYS_PROGRAMS = ["echo", "printf", "test", "[", "cd", "pushd", "export", "grep", "egrep", "fgrep", "sed",
                 "awk", "find", "ls", "cat", "head", "tail", "wc", "sort", "uniq", "cut", "tr", "diff", "tee",
                 "mkdir", "rm", "cp", "mv", "touch", "stat", "file", "basename", "dirname", "realpath",
                 "readlink"]
ALREADY = re.compile(r"\bMSYS2_ARG_CONV_EXCL=|\bMSYS_NO_PATHCONV=")
CMD_SWITCH = re.compile(r"(?<=[ \t])/[cCkK](?=[ \t]|$)")
TO_NUL = re.compile(r"(?<![\w/.])((?:\d|&)?>>?)[ \t]*((?i:nul))(?![\w./])")


def excluded(simples: tuple[shell.SimpleCommand, ...], options: Mapping[str, Any]) -> list[str]:
    """The prefixes of the arguments Git Bash would turn into paths, in the order the command names them."""
    found: list[str] = []
    for simple in simples:
        if simple.name in options["msys_programs"] or simple.name == "cmd":
            continue
        for word in simple.words[1:]:
            prefix = paths.msys_prefix(word, options["posix_roots"])
            prefix = prefix or next((named for named in options["prefixes"] if word.startswith(named)), None)
            if prefix and prefix not in found and not re.search(r"[;'\s]", prefix):
                found.append(prefix)
    return found


class WinPaths(Check):
    meta = CheckMeta(
        id="win.paths", layer=Layer.TRANSPORT, events=frozenset({HookEvent.PRE_TOOL_USE}),
        tools=frozenset({Tool.BASH}), platforms=frozenset({"win32"}), severity=Severity.FIXED,
        cost=Cost.CHEAP, reads=frozenset({"command"}), writes=frozenset({"command"}),
        after=frozenset({"shell.lint"}),
        config={
            "posix_roots": ConfigKey(list, POSIX_ROOTS, "First path segments Git Bash may turn into Windows "
                                     "paths, beside a drive letter, such as tmp in /tmp/x. A project's list "
                                     "replaces it."),
            "msys_programs": ConfigKey(list, MSYS_PROGRAMS, "Programs Git Bash runs without converting "
                                       "their arguments, whose slash arguments io-guard leaves alone. A "
                                       "project's list replaces it."),
            "prefixes": ConfigKey(list, [], "Argument prefixes Git Bash must always pass as written, beside "
                                  "the ones io-guard finds. A project's list replaces it."),
        },
        codes=frozenset({Code.MSYS_PATH, Code.RESERVED_NAME}),
        description="Keeps Git Bash from turning slash arguments into paths, and a redirect to nul into a "
                    "file.")

    def run(self, event: Event, ctx: Context) -> Decision:
        command = event.command or ""
        found = shell.scan(command)
        simples = shell.commands(command, found)
        edits: list[tuple[int, int, str]] = []
        notes: list[str] = []
        codes: list[Code] = []
        prefixes = [] if ALREADY.search(command) else excluded(simples, self.options)
        if prefixes:
            codes.append(Code.MSYS_PATH)
            notes.append(f"io-guard exported MSYS2_ARG_CONV_EXCL='{';'.join(prefixes)}', so Git Bash passes "
                         f"{', '.join(prefixes)} as written instead of turning them into paths under its "
                         f"install folder.")
        switches = [match for simple in simples if simple.name == "cmd"
                    for match in CMD_SWITCH.finditer(command, *simple.span)
                    if found.states[match.start()] == shell.NORMAL]
        if switches:
            edits += [(match.start(), match.start(), "/") for match in switches]
            codes.append(Code.MSYS_PATH)
            notes.append("io-guard wrote cmd //c, because Git Bash turns a lone /c into C:/ and cmd then "
                         "runs nothing.")
        nuls = [match for match in TO_NUL.finditer(command) if found.states[match.start(1)] == shell.NORMAL]
        if nuls:
            edits += [(match.start(2), match.end(2), "/dev/null") for match in nuls]
            codes.append(Code.RESERVED_NAME)
            operator, name = nuls[0][1], nuls[0][2]
            notes.append(f"io-guard wrote {operator}/dev/null for {operator}{name}, because Git Bash writes "
                         f"a redirect to nul into a real file named nul, which Windows tools cannot delete.")
        if not codes:
            return Decision.observe(self.meta.id)
        rewritten = command
        for start, end, text in sorted(edits, reverse=True):
            rewritten = rewritten[:start] + text + rewritten[end:]
        if prefixes:
            rewritten = f"export MSYS2_ARG_CONV_EXCL='{';'.join(prefixes)}'; {rewritten}"
        rewrite = Rewrite(self.meta.id, frozenset({"command"}), lambda given: {**given, "command": rewritten},
                          " ".join(notes), codes[0])
        return Decision(self.meta.id, Verdict.ALLOW, rewrite=rewrite)
