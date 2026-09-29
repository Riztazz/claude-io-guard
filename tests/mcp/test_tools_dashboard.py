"""io.config reads one setting, writes it into the user's or the project's config file as the loader would
accept it, refuses what the file may not hold, and the next hook call runs with it."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ioguard.checks.registry import Registry
from ioguard.hooks import entry
from ioguard.lib.context import Context, LiveFs
from ioguard.lib.platform import detect
from ioguard.lib.results import Code
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_dashboard import ConfigInput, configure
from ioguard.mcp.toolspec import ToolCall, ToolFailure
from tests.support.project import TemporaryProject


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="ioguard-config-"))
        self.addCleanup(shutil.rmtree, self.home, True)
        self.ctx = Context.fake(platform=detect(), fs=LiveFs(), data_dir=self.home)

    def call(self, root: Path, **given):
        return configure(ConfigInput(**given), ToolCall(lambda: self.ctx, CancelToken(), root, None))

    def refusal(self, root: Path, **given):
        with self.assertRaises(ToolFailure) as failure:
            self.call(root, **given)
        return failure.exception.result


class ASettingIsReadAndWritten(ConfigTest):
    def test_reading_writes_nothing_and_names_the_default_in_force(self):
        with TemporaryProject(git=True) as root:
            done = self.call(root, key="checks.shell.lint.enabled")
        self.assertEqual((done.before, done.applies, done.written, (self.home / "config.json").exists()),
                         (None, True, False, False), "a read names the value in force and creates no file")

    def test_a_user_write_lands_in_io_guards_folder_and_applies(self):
        with TemporaryProject(git=True) as root:
            done = self.call(root, key="transport.rewrite_mode.auto", value="ask")
        written = json.loads((self.home / "config.json").read_bytes())
        self.assertEqual((written, done.before, done.after, done.applies, done.written),
                         ({"schema": 1, "transport": {"rewrite_mode": {"auto": "ask"}}}, None, "ask", "ask",
                          True), "the user file holds the value, and it is in force")

    def test_a_project_write_joins_the_projects_file_and_a_remove_clears_it(self):
        existing = json.dumps({"schema": 1, "checks": {"shell.lint": {"build_commands": ["make"]}}})
        with TemporaryProject({".claude/io-guard.json": existing.encode()}, git=True) as root:
            self.call(root, key="checks.shell.lint.enabled", value=False, scope="project")
            added = json.loads((root / ".claude" / "io-guard.json").read_bytes())
            removed = self.call(root, key="checks.shell.lint.enabled", scope="project", remove=True)
            left = json.loads((root / ".claude" / "io-guard.json").read_bytes())
        self.assertEqual(added["checks"]["shell.lint"], {"build_commands": ["make"], "enabled": False},
                         "the setting joins the check's own object")
        self.assertEqual((left, removed.applies), (json.loads(existing), True),
                         "a remove leaves the file as it was, and the default applies again")


class WhatTheFileMayNotHoldIsRefused(ConfigTest):
    def test_each_refusal_names_why_and_writes_nothing(self):
        cases = {"an unknown key": dict(key="checks.shell.lnt.enabled", value=False),
                 "a wrong type": dict(key="checks.shell.lint.enabled", value="no"),
                 "a value outside the choices": dict(key="transport.rewrite_mode.auto", value="maybe"),
                 "a key only the user may set": dict(key="verify", value={}, scope="project"),
                 "a value a project may not set": dict(key="transport.rewrite_mode.auto", value="allow",
                                                       scope="project"),
                 "a number a project may only lower": dict(key="transport.budget_bytes", value=9000,
                                                          scope="project"),
                 "an unknown scope": dict(key="checks.shell.lint.enabled", value=False, scope="everyone")}
        with TemporaryProject(git=True) as root:
            for name, given in cases.items():
                with self.subTest(name=name):
                    self.assertEqual(self.refusal(root, **given).code, Code.CONFIG_REFUSED,
                                     "the loader would drop such a file, so io.config refuses it")
            files = [(self.home / "config.json").exists(), (root / ".claude" / "io-guard.json").exists()]
        self.assertEqual(files, [False, False], "no refused call writes a file")

    def test_an_unknown_key_names_the_nearest(self):
        with TemporaryProject(git=True) as root:
            result = self.refusal(root, key="checks.shell.lnt.enabled", value=False)
        self.assertIn("The nearest is checks.shell.lint.enabled.", result.message, "the typo's fix is named")


class TheNextCallRunsWithIt(ConfigTest):
    def test_a_session_already_running_sees_the_write(self):
        contexts = entry.LiveContexts()
        key = "transport.rewrite_mode.default"
        with TemporaryProject(git=True) as root, \
                mock.patch.dict(os.environ, {"IOGUARD_HOME": str(self.home)}):
            before = contexts.get("s1", root, Registry()).config.get(key)
            self.call(root, key=key, value="refuse")
            after = contexts.get("s1", root, Registry()).config.get(key)
        self.assertEqual((before, after), ("ask", "refuse"),
                         "the hooks load the changed file on their next call")


if __name__ == "__main__":
    unittest.main()
