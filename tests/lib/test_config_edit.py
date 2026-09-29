"""config_edit places one setting where the file already keeps its neighbours, and removes it cleanly."""
import json
import unittest

from ioguard.lib import config_edit
from ioguard.lib.config import Scope, all_keys, flatten, validate
from ioguard.checks.registry import default_registry

KEYS = all_keys(default_registry().keys())
PROJECT = {"schema": 1, "checks": {"shell.lint": {"build_commands": ["make"]}}}


class ASettingLandsBesideItsNeighbours(unittest.TestCase):
    def test_a_check_option_joins_the_checks_own_object(self):
        out = config_edit.placed(PROJECT, "checks.shell.lint.enabled", False)
        self.assertEqual(out["checks"]["shell.lint"], {"build_commands": ["make"], "enabled": False},
                         "the option goes under the check's existing object")

    def test_a_new_check_nests_by_its_id_and_a_global_key_by_its_dots(self):
        out = config_edit.placed({"schema": 1}, "checks.verify.write.repair", False)
        out = config_edit.placed(out, "transport.rewrite_mode.auto", "ask")
        self.assertEqual(out, {"schema": 1, "checks": {"verify.write": {"repair": False}},
                               "transport": {"rewrite_mode": {"auto": "ask"}}},
                         "checks > id > option, and one level per dot elsewhere")

    def test_a_file_nested_another_way_keeps_its_way(self):
        raw = {"checks": {"shell": {"lint": {"enabled": True}}}}
        self.assertEqual(config_edit.placed(raw, "checks.shell.lint.enabled", False),
                         {"checks": {"shell": {"lint": {"enabled": False}}}},
                         "an existing path is followed, never a second copy of the key")

    def test_every_placed_key_reads_back_as_the_loader_reads_it(self):
        out = PROJECT
        settings = (("checks.shell.lint.enabled", False), ("noise_patterns", ["^x"]),
                    ("transport.rewrite_mode.plan", "refuse"), ("verify", {".py": ["python", "{file}"]}))
        for key, value in settings:
            out = config_edit.placed(out, key, value)
            with self.subTest(key=key):
                self.assertEqual((flatten(out, KEYS)[key], config_edit.value_at(out, key)), (value, value),
                                 "the loader and value_at both find the value where it was placed")
        self.assertEqual(validate(out, Scope.USER, KEYS), (), "the file still loads")

    def test_a_removed_key_takes_the_objects_it_empties(self):
        out = config_edit.placed(PROJECT, "checks.shell.lint.build_commands", None)
        self.assertEqual(out, {"schema": 1}, "nothing empty is left behind")
        self.assertEqual(config_edit.placed(PROJECT, "noise_patterns", None), PROJECT,
                         "removing a key the file lacks changes nothing")

    def test_the_input_is_never_changed_and_the_bytes_are_ascii_json(self):
        before = json.dumps(PROJECT)
        data = config_edit.encoded(config_edit.placed(PROJECT, "skip_trees", ["Content/**"]))
        self.assertEqual((json.dumps(PROJECT), data.endswith(b"\n"), data.isascii()), (before, True, True),
                         "a copy is changed, and the bytes end in a newline")


if __name__ == "__main__":
    unittest.main()
