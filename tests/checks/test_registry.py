"""The registry refuses a malformed check at registration, and selects the enabled checks that apply."""
import unittest
from pathlib import Path

from ioguard.checks.registry import Registry, RegistryError, default_registry
from ioguard.lib import config
from ioguard.lib.config import ConfigKey
from ioguard.lib.context import Context
from ioguard.lib.events import Event, Surface, Tool
from tests.support import events
from tests.support.checks import make_check


def bash_event() -> Event:
    return Event.from_hook_json(events.bash("ls", Path("C:/p")), Surface.COMMAND_HOOK)


class RegistrationRefusesBrokenChecks(unittest.TestCase):
    def assertRefused(self, check_class, fragment: str, registry: Registry | None = None) -> None:
        with self.assertRaisesRegex(RegistryError, fragment):
            (registry or Registry()).register(check_class)

    def test_a_taken_id_is_refused(self):
        registry = Registry()
        registry.register(make_check("demo.one"))
        self.assertRefused(make_check("demo.one"), "taken", registry)

    def test_a_code_outside_codes_is_refused(self):
        self.assertRefused(make_check("demo.two", codes=("NOT_A_CODE",)), "not in CODES")

    def test_running_after_an_unregistered_check_is_refused(self):
        self.assertRefused(make_check("demo.three", after=("demo.missing",)), "demo.missing")

    def test_a_config_key_with_a_wrong_default_is_refused(self):
        self.assertRefused(make_check("demo.four", config={"limit": ConfigKey(int, "5", "x")}), "limit")

    def test_redefining_enabled_is_refused(self):
        self.assertRefused(make_check("demo.five", config={"enabled": ConfigKey(bool, True, "x")}), "enabled")

    def test_a_class_without_meta_is_refused(self):
        self.assertRefused(type("NoMeta", (), {}), "no CheckMeta")


class RegistrySelects(unittest.TestCase):
    def test_a_disabled_check_is_not_selected(self):
        registry = Registry()
        registry.register(make_check("demo.on"))
        registry.register(make_check("demo.off"))
        values = {**config.defaults(registry.keys()).values, "checks.demo.off.enabled": False}
        ctx = Context.fake(config=config.Config(values))
        self.assertEqual([check.meta.id for check in registry.select(bash_event(), ctx)], ["demo.on"],
                         "checks.<id>.enabled false keeps a check out of the run")

    def test_a_check_for_another_tool_is_not_selected(self):
        registry = Registry()
        registry.register(make_check("demo.edit", tools=(Tool.EDIT,)))
        self.assertEqual(registry.select(bash_event(), Context.fake()), (),
                         "a check that names Edit does not run on a Bash event")

    def test_a_check_for_another_platform_is_not_selected(self):
        registry = Registry()
        registry.register(make_check("demo.plan9", platforms=frozenset({"plan9"})))
        self.assertEqual(registry.select(bash_event(), Context.fake()), (),
                         "a check runs only on the platforms it names")

    def test_options_come_from_the_config(self):
        registry = Registry()
        registry.register(make_check("demo.opts", config={"limit": ConfigKey(int, 5, "x")}))
        values = {**config.defaults(registry.keys()).values, "checks.demo.opts.limit": 9}
        check = registry.instantiate(config.Config(values))[0]
        self.assertEqual(dict(check.options), {"enabled": True, "limit": 9},
                         "a check receives its own keys from checks.<id>")

    def test_the_default_registry_loads(self):
        self.assertIsInstance(default_registry(), Registry, "the shipped list of checks registers cleanly")


if __name__ == "__main__":
    unittest.main()
