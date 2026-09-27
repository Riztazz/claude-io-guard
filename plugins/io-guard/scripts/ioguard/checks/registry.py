"""The one list of checks, validated as each is registered."""
from collections.abc import Mapping

from ioguard.checks.base import Check, CheckMeta
from ioguard.checks.session_probe import SessionProbe
from ioguard.lib.config import Config, ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.events import Event
from ioguard.lib.results import Code

KEY_TYPES = (bool, int, str, list, dict)


class RegistryError(Exception):
    """A check class that breaks the rules of registration. It is a bug in that check."""


def problems(check_class: type[Check], known: Mapping[str, type[Check]]) -> list[str]:
    """What is wrong with a check class, against the checks already registered."""
    meta = getattr(check_class, "meta", None)
    if not isinstance(meta, CheckMeta):
        return [f"{check_class.__name__} has no CheckMeta in meta."]
    found = []
    if meta.id in known:
        found.append(f"the id {meta.id} is taken by {known[meta.id].__name__}")
    if not meta.events:
        found.append("it names no hook event")
    if not meta.platforms:
        found.append("it names no platform")
    found += [f"{code!r} is not in CODES" for code in meta.codes if not isinstance(code, Code)]
    found += [f"it runs after {other}, which is not registered before it"
              for other in sorted(meta.after) if other not in known]
    for name, key in meta.config.items():
        if name == "enabled":
            found.append("it redefines the enabled key every check has")
        elif not isinstance(key, ConfigKey) or key.type not in KEY_TYPES:
            found.append(f"its config key {name} has no type io-guard reads")
        elif not isinstance(key.default, key.type) or (key.type is int and isinstance(key.default, bool)):
            found.append(f"its config key {name} has a default that is not a {key.type.__name__}")
    return found


class Registry:
    def __init__(self) -> None:
        self.classes: dict[str, type[Check]] = {}

    def register(self, check_class: type[Check]) -> None:
        """Add a check class. A check that runs after another is registered after it, so the order has no
        cycle by construction."""
        found = problems(check_class, self.classes)
        if found:
            raise RegistryError(f"{check_class.__name__} cannot be registered: {'; '.join(found)}.")
        self.classes[check_class.meta.id] = check_class

    def ids(self) -> tuple[str, ...]:
        return tuple(self.classes)

    def keys(self) -> dict[str, Mapping[str, ConfigKey]]:
        """Each check's own config keys, which lib.config adds under checks.<id>."""
        return {check_id: check_class.meta.config for check_id, check_class in self.classes.items()}

    def instantiate(self, config: Config) -> tuple[Check, ...]:
        return tuple(check_class(config.check_options(check_id))
                     for check_id, check_class in self.classes.items())

    def select(self, event: Event, ctx: Context) -> tuple[Check, ...]:
        """The enabled checks that apply to this event."""
        return tuple(check for check in self.instantiate(ctx.config)
                     if check.options.get("enabled", True) and check.applies(event, ctx))


CHECKS: tuple[type[Check], ...] = (SessionProbe,)


def default_registry() -> Registry:
    """Every check io-guard ships. Each check joins CHECKS in the task that builds it, after the checks it
    runs after."""
    registry = Registry()
    for check_class in CHECKS:
        registry.register(check_class)
    return registry
