"""Checks a test puts into io-guard's registry, each giving one shape of answer, and install, which adds them.

inject/sitecustomize.py installs the ones IOGUARD_TEST_CHECKS names into a Python a test starts, so hook.py
and ioguard_mcp.py run with them as shipped. A live check starts Claude Code with the same variables.
"""
import os
from collections.abc import Iterable
from pathlib import Path

from ioguard.checks.base import Check, Cost
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision, Rewrite, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Fix, Layer, Result, Severity
from tests.support.checks import make_check

ORIGINAL = "IOGUARD_ORIGINAL"
REWRITTEN = "IOGUARD_REWRITTEN"
REFUSE = "IOGUARD_REFUSE"
NOTE = "IOGUARD-TEST-NOTE"
OUTPUT = "IOGUARD-TEST-OUTPUT"
CLASSIFIER = "IOGUARD-TEST-CLASSIFIER"
BROKEN = "IOGUARD-TEST-BROKEN"
DIE = "IOGUARD_DIE"
EVERY_EVENT = (HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE, HookEvent.POST_TOOL_USE_FAILURE,
               HookEvent.SESSION_START)
SHELLS = (Tool.BASH, Tool.POWERSHELL)


def note(check: Check, event: Event, ctx: Context) -> Decision:
    return Decision("test.note", Verdict.ALLOW, context=(f"{NOTE} {event.kind.value} {event.tool_name}",))


def rewrite(check: Check, event: Event, ctx: Context) -> Decision:
    if ORIGINAL not in (event.command or ""):
        return Decision.observe("test.rewrite")
    swap = Rewrite("test.rewrite", frozenset({"command"}),
                   lambda given: {**given, "command": given["command"].replace(ORIGINAL, REWRITTEN)},
                   "io-guard's test check rewrote the command.", Code.REWRITE_CONFLICT)
    return Decision("test.rewrite", Verdict.ALLOW, rewrite=swap)


def refuse(check: Check, event: Event, ctx: Context) -> Decision:
    if REFUSE not in (event.command or ""):
        return Decision.observe("test.refuse")
    fix = Fix(event.tool_name, {"command": "echo IOGUARD_ALLOWED"}, "Run echo IOGUARD_ALLOWED instead.")
    result = Result.of(Code.GUARD_ERROR, "io-guard's test check refused this command.", event.tool_name,
                       ctx.platform.os, severity=Severity.REFUSED, fix=fix)
    return Decision("test.refuse", Verdict.DENY, results=(result,))


def output(check: Check, event: Event, ctx: Context) -> Decision:
    replaced = {**(event.tool_response or {}), "stdout": OUTPUT}
    return Decision("test.output", Verdict.ALLOW, output_replacement=replaced, classifier_note=CLASSIFIER)


def broken(check: Check, event: Event, ctx: Context) -> Decision:
    raise RuntimeError(BROKEN)


def die(check: Check, event: Event, ctx: Context) -> Decision:
    """End the process on a command naming DIE, after marking it dead for good through IOGUARD_TEST_DEAD,
    which inject/sitecustomize.py reads at the next start."""
    if DIE in (event.command or ""):
        marker = os.environ.get("IOGUARD_TEST_DEAD")
        if marker:
            Path(marker).write_bytes(b"dead\n")
        os._exit(3)
    return Decision.observe("test.die")


CHECKS: dict[str, type[Check]] = {
    "broken": make_check("test.broken", broken, layer=Layer.LOCATION, events=EVERY_EVENT),
    "refuse": make_check("test.refuse", refuse, layer=Layer.LOCATION, tools=SHELLS),
    "rewrite": make_check("test.rewrite", rewrite, writes=("command",), tools=SHELLS,
                          codes=(Code.REWRITE_CONFLICT,)),
    "note": make_check("test.note", note, layer=Layer.READ, cost=Cost.MEDIUM, events=EVERY_EVENT),
    "output": make_check("test.output", output, layer=Layer.OUTPUT, events=(HookEvent.POST_TOOL_USE,),
                         tools=(Tool.BASH,)),
    "die": make_check("test.die", die, layer=Layer.LOCATION, tools=SHELLS),
}


def install(names: Iterable[str]) -> None:
    """Add the named checks to the checks io-guard ships, as default_registry reads them."""
    from ioguard.checks import registry
    registry.CHECKS = registry.CHECKS + tuple(CHECKS[name] for name in names)
