"""Check classes built for a test: an id, a place in the order, and a run the test supplies."""
from collections.abc import Callable, Iterable

from ioguard.checks.base import Check, CheckMeta, Cost
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import Code, Layer, Severity

EVERY_PLATFORM = frozenset({"win32", "darwin", "linux"})


def make_check(check_id: str, decide: Callable[[Check, Event, Context], Decision] | None = None, *,
               layer: Layer = Layer.TRANSPORT, cost: Cost = Cost.CHEAP, after: Iterable[str] = (),
               writes: Iterable[str] = (), tools: Iterable[Tool] = (),
               events: Iterable[HookEvent] = (HookEvent.PRE_TOOL_USE,),
               platforms: frozenset[str] = EVERY_PLATFORM,
               codes: Iterable[Code] = (), config: dict[str, ConfigKey] | None = None,
               module: str = "tests.support.checks") -> type[Check]:
    """A Check subclass whose run calls decide, or observes when decide is None."""
    meta = CheckMeta(id=check_id, layer=layer, events=frozenset(events),
                     tools=frozenset(tools), platforms=platforms, severity=Severity.WARNING, cost=cost,
                     reads=frozenset(), writes=frozenset(writes), after=frozenset(after), config=config or {},
                     codes=frozenset(codes), description="A check a test built.")

    def run(self: Check, event: Event, ctx: Context) -> Decision:
        return Decision.observe(check_id) if decide is None else decide(self, event, ctx)

    return type(f"TestCheck_{check_id.replace('.', '_')}", (Check,),
                {"meta": meta, "run": run, "__module__": module})
