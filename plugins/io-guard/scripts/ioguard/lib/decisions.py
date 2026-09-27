"""What a check decides about one call, and how the pipeline chains the rewrites checks propose."""
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType
from typing import Any

from ioguard.lib.results import Code, Result


class Verdict(IntEnum):
    OBSERVE = 0          # nothing to say
    ALLOW = 1            # say something, and let the call run
    ASK = 2              # show the input to the user
    DENY = 3             # refuse, with the fix


class RewriteError(Exception):
    """A rewrite changed a tool_input field it did not declare, which is a bug in its check."""


@dataclass(frozen=True)
class Rewrite:
    check_id: str
    fields: frozenset[str]                                  # the tool_input keys it changes
    apply: Callable[[Mapping[str, Any]], Mapping[str, Any]]  # the whole tool_input in, the whole one out
    note: str                                               # the additionalContext line
    code: Code
    exclusive: bool = False                                 # it refuses to share its fields


@dataclass(frozen=True)
class Decision:
    check_id: str
    verdict: Verdict
    results: tuple[Result, ...] = ()
    rewrite: Rewrite | None = None
    context: tuple[str, ...] = ()                           # lines for the model
    user_message: str | None = None                         # rare, shown once per session key
    classifier_note: str | None = None                      # PostToolUse classifierContext
    output_replacement: Mapping[str, Any] | None = None     # PostToolUse updatedToolOutput
    latency_ms: float = 0.0

    @staticmethod
    def observe(check_id: str) -> "Decision":
        return Decision(check_id, Verdict.OBSERVE)


@dataclass(frozen=True)
class Conflict:
    dropped: Rewrite
    kept: Rewrite


@dataclass(frozen=True)
class ComposeResult:
    tool_input: Mapping[str, Any]
    applied: tuple[Rewrite, ...]
    conflicts: tuple[Conflict, ...]


def conflict_with(rewrite: Rewrite, applied: Sequence[Rewrite]) -> Rewrite | None:
    """The applied rewrite this one may not follow: one that shares a field, where either is exclusive."""
    return next((earlier for earlier in applied
                 if earlier.fields & rewrite.fields and (earlier.exclusive or rewrite.exclusive)), None)


def apply_one(rewrite: Rewrite, tool_input: Mapping[str, Any]) -> dict[str, Any]:
    after = dict(rewrite.apply(MappingProxyType(dict(tool_input))))
    changed = {key for key in tool_input.keys() | after.keys() if tool_input.get(key) != after.get(key)}
    undeclared = changed - rewrite.fields
    if undeclared:
        raise RewriteError(f"{rewrite.check_id} changed {sorted(undeclared)}, which it does not declare.")
    return after


def compose(rewrites: Sequence[Rewrite], tool_input: Mapping[str, Any]) -> ComposeResult:
    """Apply the rewrites in order. Disjoint fields compose, and a shared field composes unless either
    rewrite is exclusive, in which case the later one is dropped as a conflict."""
    running, applied, conflicts = dict(tool_input), [], []
    for rewrite in rewrites:
        earlier = conflict_with(rewrite, applied)
        if earlier is not None:
            conflicts.append(Conflict(dropped=rewrite, kept=earlier))
            continue
        running = apply_one(rewrite, running)
        applied.append(rewrite)
    return ComposeResult(MappingProxyType(running), tuple(applied), tuple(conflicts))
