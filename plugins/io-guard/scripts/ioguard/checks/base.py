"""What every check is: one class with one run, and a CheckMeta that declares what it touches."""
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, ClassVar

from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Layer, Severity


class Cost(IntEnum):
    CHEAP = 5            # estimated milliseconds, no IO beyond the event
    MEDIUM = 50          # reads files
    EXPENSIVE = 500      # starts a program


@dataclass(frozen=True)
class CheckMeta:
    id: str                                  # "transport.body", stable forever
    layer: Layer
    events: frozenset[HookEvent]
    tools: frozenset[Tool]                   # empty means every tool
    platforms: frozenset[str]                # lib.platform's names, EVERY_PLATFORM for most checks
    severity: Severity                       # the default when the check finds something
    cost: Cost
    reads: frozenset[str]                    # tool_input fields it reads
    writes: frozenset[str]                   # tool_input fields its rewrite changes
    after: frozenset[str]                    # check ids that must run first
    config: Mapping[str, ConfigKey]          # its own keys under checks.<id>
    codes: frozenset[Code]                   # every code it can produce
    description: str                         # one sentence for the skill


class Check(ABC):
    """A check holds its options and nothing else. It returns a Decision for everything expected, and raises
    only on a bug, which the pipeline logs and steps over."""
    meta: ClassVar[CheckMeta]

    def __init__(self, options: Mapping[str, Any]) -> None:
        self.options = options

    def applies(self, event: Event, ctx: Context) -> bool:
        return (event.kind in self.meta.events
                and (not self.meta.tools or event.tool in self.meta.tools)
                and ctx.probe.os in self.meta.platforms)

    @abstractmethod
    def run(self, event: Event, ctx: Context) -> Decision: ...
