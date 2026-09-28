"""The config's four layers: defaults in code, the user's file, and project files that never widen."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ioguard.checks.registry import default_registry
from ioguard.lib import config
from ioguard.lib.config import ConfigKey, ConfigLayer, Scope

AUTO_ALLOW = {"transport": {"rewrite_mode": {"auto": "allow"}}}
REAL_KEYS = default_registry().keys()
CHECK_KEYS = {"demo.check": {"limit": ConfigKey(int, 5, "A demo limit."),
                             "roots_extra": ConfigKey(list, [], "Extra roots.", project_may_set=False)}}


class ConfigFiles(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="ioguard-config-"))

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)

    def layer(self, scope: Scope, name: str, content) -> ConfigLayer:
        path = self.folder / name
        data = content if isinstance(content, bytes) else json.dumps(content).encode("ascii")
        path.write_bytes(data)
        return ConfigLayer(scope, path)

    def load(self, *layers: ConfigLayer) -> config.LoadReport:
        return config.load(layers, CHECK_KEYS)


class DefaultsLiveInCode(ConfigFiles):
    def test_the_budget_defaults_are_300_and_2000_ms(self):
        values = config.defaults().values
        self.assertEqual((values["pipeline.soft_ms"], values["pipeline.hard_ms"]), (300, 2000),
                         "the time budget defaults are the ones D16 set")

    def test_the_rewrite_modes_default_as_d12_says(self):
        values = config.defaults().values
        modes = {mode: values[f"transport.rewrite_mode.{mode}"] for mode in config.REWRITE_DEFAULTS}
        self.assertEqual(modes, {"default": "ask", "acceptEdits": "ask", "plan": "ask", "auto": "refuse",
                                 "dontAsk": "refuse", "bypassPermissions": "allow"},
                         "each permission mode has D12's default rewrite mode")

    def test_every_check_gets_an_enabled_key_and_its_own_keys(self):
        values = config.defaults(CHECK_KEYS).values
        self.assertEqual((values["checks.demo.check.enabled"], values["checks.demo.check.limit"]), (True, 5),
                         "a check's keys sit under checks.<id>, with enabled on by default")

    def test_missing_files_leave_the_defaults(self):
        report = self.load(ConfigLayer(Scope.USER, self.folder / "absent.json"))
        self.assertEqual((report.errors, report.config.get("pipeline.soft_ms")), ((), 300),
                         "a layer whose file does not exist is not an error")


class LayersMerge(ConfigFiles):
    def test_the_user_file_overrides_a_default(self):
        report = self.load(self.layer(Scope.USER, "user.json", {"pipeline": {"soft_ms": 150}}))
        self.assertEqual(report.config.get("pipeline.soft_ms"), 150, "a user value replaces the default")

    def test_a_later_layer_wins_key_by_key(self):
        user = {"pipeline": {"soft_ms": 150, "hard_ms": 900}}
        report = self.load(self.layer(Scope.USER, "user.json", user),
                           self.layer(Scope.PROJECT, "project.json", {"pipeline": {"soft_ms": 100}}))
        self.assertEqual((report.config.get("pipeline.soft_ms"), report.config.get("pipeline.hard_ms")),
                         (100, 900), "the project sets one key, and the user's other key stays")

    def test_a_list_ending_in_extra_appends(self):
        merged = config.merge({"write_roots.extra": ["a"], "skip": ["x"]},
                              {"write_roots.extra": ["b"], "skip": ["y"]})
        self.assertEqual((merged["write_roots.extra"], merged["skip"]), (["a", "b"], ["y"]),
                         "a list key ending in extra appends, and any other list replaces")

    def test_a_dict_value_merges_into_the_base_dict(self):
        merged = config.merge({"verify": {".py": ["a"]}}, {"verify": {".js": ["b"]}})
        self.assertEqual(merged["verify"], {".py": ["a"], ".js": ["b"]}, "dictionaries deep-merge")


class ProjectsNeverWiden(ConfigFiles):
    def test_a_project_may_not_set_allow_as_a_rewrite_mode(self):
        report = self.load(self.layer(Scope.PROJECT, "p.json", AUTO_ALLOW))
        self.assertEqual((report.config.get("transport.rewrite_mode.auto"), len(report.dropped)),
                         ("refuse", 1), "a project file that sets allow is dropped, and the default stays")

    def test_the_user_may_set_allow(self):
        report = self.load(self.layer(Scope.USER, "u.json", AUTO_ALLOW))
        self.assertEqual(report.config.get("transport.rewrite_mode.auto"), "allow",
                         "the rewrite mode is the user's to choose (D12)")

    def test_a_project_may_not_turn_telemetry_off(self):
        report = self.load(self.layer(Scope.PROJECT_LOCAL, "l.json", {"telemetry": {"enabled": False}}))
        self.assertTrue(report.config.get("telemetry.enabled"),
                        "a project-local file cannot turn telemetry off")

    def test_a_project_may_not_set_a_user_only_check_key(self):
        report = self.load(self.layer(Scope.PROJECT, "p.json",
                                      {"checks": {"demo.check": {"roots_extra": ["C:/elsewhere"]}}}))
        self.assertIn("A project file may not set this key", report.errors[0].message,
                      "a key marked project_may_set=False is refused in a project file")

    def test_a_project_file_that_sets_verify_is_dropped_whole(self):
        project = self.layer(Scope.PROJECT, "p.json", {"verify": {".py": ["python", "evil.py", "{file}"]},
                                                       "transport": {"budget_bytes": 5000}})
        report = self.load(project)
        self.assertEqual((report.errors[0].key, report.dropped, report.config.get("verify")),
                         ("verify", (project.path,), {}),
                         "a project may not name a command io-guard runs, and none of its file loads")
        self.assertIn("your own config.json", report.errors[0].message, "the error names where verify goes")

    def test_the_user_sets_verify_and_a_bad_shape_is_an_error(self):
        good = {".py": ["python", "-m", "py_compile", "{file}"]}
        loaded = self.load(self.layer(Scope.USER, "u.json", {"verify": good}))
        broken = self.load(self.layer(Scope.USER, "b.json", {"verify": {".py": "python {file}"}}))
        self.assertEqual((loaded.config.get("verify"), broken.errors[0].key), (good, "verify"),
                         "the user's command loads, and a command that is not a list drops the file")

    def lists(self, ascii_only: list, prefixes: list, builds: list) -> dict:
        return {"checks": {"verify.write": {"ascii_only": ascii_only}, "win.paths": {"prefixes": prefixes},
                           "shell.lint": {"build_commands": builds}}}

    def test_a_projects_list_adds_to_a_stricter_list_and_replaces_the_others(self):
        user = self.layer(Scope.USER, "u.json", self.lists([".py", ".md"], ["--a="], ["make"]))
        cases = {"adds": ([".txt"], [".py", ".md", ".txt"]), "shrinks": ([], [".py", ".md"]),
                 "repeats": ([".md"], [".py", ".md"])}
        for name, (project, expected) in cases.items():
            with self.subTest(name):
                given = self.layer(Scope.PROJECT, "p.json", self.lists(project, ["--b="], ["ninja"]))
                values = config.load((user, given), REAL_KEYS).config.values
                found = [values[f"checks.{key}"] for key in ("verify.write.ascii_only", "win.paths.prefixes",
                                                            "shell.lint.build_commands")]
                self.assertEqual(found, [expected, ["--a=", "--b="], ["ninja"]],
                                 "a project can add to a stricter list, never drop from it, and replaces a "
                                 "list of its own tools")

    def test_the_user_may_still_shorten_a_stricter_list(self):
        user = self.layer(Scope.USER, "u.json", {"checks": {"verify.write": {"ascii_only": []}}})
        found = config.load((user,), REAL_KEYS).config.get("checks.verify.write.ascii_only")
        self.assertEqual(found, [], "the user's list is the user's")

    def test_every_list_key_says_how_a_project_list_merges(self):
        def says(key: ConfigKey) -> bool:
            return f"A project's list {'adds' if key.project_joins else 'replaces'}" in key.doc

        silent = [name for name, key in config.all_keys(REAL_KEYS).items()
                  if key.type is list and key.project_may_set and not says(key)]
        self.assertEqual(silent, [], "each list key's text names the merge its flag gives")

    def test_a_project_may_lower_the_transport_budget(self):
        report = self.load(self.layer(Scope.PROJECT, "p.json", {"transport": {"budget_bytes": 4000}}))
        self.assertEqual(report.config.get("transport.budget_bytes"), 4000,
                         "narrowing is what a project may do")

    def test_a_project_may_not_raise_it_past_the_layers_below(self):
        report = self.load(self.layer(Scope.USER, "u.json", {"transport": {"budget_bytes": 5000}}),
                           self.layer(Scope.PROJECT, "p.json", {"transport": {"budget_bytes": 5500}}))
        self.assertEqual(report.config.get("transport.budget_bytes"), 5000,
                         "the user's 5,000 holds against the project's 5,500")
        self.assertIn("may lower this number and not raise it past 5000", report.errors[0].message,
                      "the error names the value the project may not pass")

    def test_a_project_regex_that_could_stall_is_refused_and_the_users_is_not(self):
        stalls = {"noise_patterns": ["^(a+)+$"]}
        project = self.load(self.layer(Scope.PROJECT, "p.json", stalls))
        user = self.load(self.layer(Scope.USER, "u.json", stalls))
        self.assertEqual((project.errors[0].key, project.config.get("noise_patterns")),
                         ("noise_patterns", []),
                         "a cloned repository cannot make io-guard run a pattern that backtracks")
        self.assertEqual((user.errors, user.config.get("noise_patterns")), ((), ["^(a+)+$"]),
                         "the user's own file may set it")


class BadFilesAreDroppedWhole(ConfigFiles):
    def test_an_unknown_key_drops_the_file_and_names_the_nearest_key(self):
        path = self.layer(Scope.USER, "user.json", {"pipeline": {"soft_ms": 10, "hard_mz": 5}})
        report = self.load(path)
        error = report.errors[0]
        self.assertEqual((error.file, error.key, error.nearest), (path.path, "pipeline.hard_mz",
                                                                  "pipeline.hard_ms"),
                         "the error names the file, the unknown key and the nearest known key")
        self.assertEqual(report.config.get("pipeline.soft_ms"), 300,
                         "the file is dropped whole, so its valid soft_ms does not apply either")
        self.assertIn("pipeline.hard_ms", report.user_message, "the user's one message names the fix")

    def test_a_wrong_type_is_an_error(self):
        report = self.load(self.layer(Scope.USER, "u.json", {"pipeline": {"soft_ms": "fast"}}))
        self.assertIn("must be a int", report.errors[0].message, "a string where an int belongs is refused")

    def test_a_boolean_is_not_an_int(self):
        report = self.load(self.layer(Scope.USER, "u.json", {"pipeline": {"soft_ms": True}}))
        self.assertEqual(len(report.dropped), 1, "true is not a number of milliseconds")

    def test_a_value_outside_the_choices_is_an_error(self):
        report = self.load(self.layer(Scope.USER, "u.json", {"transport": {"rewrite_mode": {"auto": "yes"}}}))
        self.assertIn("refuse, ask, allow", report.errors[0].message, "the error lists the values it takes")

    def test_a_file_that_is_not_json_says_where(self):
        report = self.load(self.layer(Scope.USER, "u.json", b'{"pipeline": }'))
        self.assertIn("line 1, column", report.errors[0].message, "a JSON error names its line and column")

    def test_a_newer_schema_warns_about_unknown_keys_and_still_loads(self):
        report = self.load(self.layer(Scope.USER, "u.json", {"schema": 99, "future": {"key": 1},
                                                            "pipeline": {"soft_ms": 120}}))
        self.assertEqual((report.errors[0].warning, report.config.get("pipeline.soft_ms")), (True, 120),
                         "a file from a newer schema loads, and its unknown keys are warnings")

    def test_a_good_file_still_loads_after_a_dropped_one(self):
        report = self.load(self.layer(Scope.USER, "u.json", {"pipeline": {"soft_ms": 150}}),
                           self.layer(Scope.PROJECT, "p.json", {"bogus": 1}))
        self.assertEqual((report.config.get("pipeline.soft_ms"), len(report.loaded)), (150, 1),
                         "the guard runs on the layers that loaded")


if __name__ == "__main__":
    unittest.main()
