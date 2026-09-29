"""io.config reads one setting, writes it into the user's or the project's config file as the loader would
accept it, refuses what the file may not hold, and the next hook call runs with it."""
import http.client
import json
import os
import shutil
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from ioguard.checks.registry import Registry
from ioguard.hooks import entry
from ioguard.lib.context import Context, LiveFs, project_root
from ioguard.lib.platform import detect
from ioguard.lib.results import Code
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_dashboard import BOARDS, ConfigInput, DashboardInput, configure, dashboard
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


class ThePageServerAnswersOnlyItsOwnPage(ConfigTest):
    def setUp(self):
        super().setUp()
        self.root = Path(tempfile.mkdtemp(prefix="ioguard-board-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / ".git").mkdir()
        call = ToolCall(lambda: self.ctx, CancelToken(), self.root, None)
        self.done = dashboard(DashboardInput(), call)
        self.again = dashboard(DashboardInput(), call)
        self.addCleanup(BOARDS.pop(project_root(self.root)).stop)
        self.port = urlsplit(self.done.url).port
        self.token = parse_qs(urlsplit(self.done.url).query)["token"][0]

    def request(self, method: str, path: str, body: bytes | None = None, token: str | None = None,
                host: str | None = None, kind: str = "application/json") -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": host or f"127.0.0.1:{self.port}", "Content-Type": kind}
        if token is not None:
            headers["X-IOGuard-Token"] = token
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        answer = (response.status, response.read())
        connection.close()
        return answer

    def test_the_tool_starts_one_server_and_the_url_opens_the_page(self):
        with urllib.request.urlopen(self.done.url, timeout=10) as response:
            page = response.read()
        self.assertEqual((self.again.url, b"<title>io-guard settings</title>" in page), (self.done.url, True),
                         "a second call gives the same page, and the URL with its token opens it")

    def test_the_settings_and_a_write_go_through_the_api(self):
        status, body = self.request("GET", "/api/settings", token=self.token)
        rows = {row["key"]: row for row in json.loads(body)["settings"]}
        sent = json.dumps({"key": "checks.shell.lint.enabled", "value": False, "scope": "project"})
        wrote, answer = self.request("POST", "/api/setting", sent.encode(), token=self.token)
        refused, why = self.request("POST", "/api/setting", json.dumps(
            {"key": "transport.rewrite_mode.auto", "value": "allow", "scope": "project"}).encode(),
            token=self.token)
        on_disk = json.loads((self.root / ".claude" / "io-guard.json").read_bytes())
        lint = rows["checks.shell.lint.enabled"]["applies"]
        self.assertEqual((status, lint, wrote, json.loads(answer)["written"]), (200, True, 200, True),
                         "the page reads every setting and writes one")
        self.assertEqual((refused, json.loads(why)["code"], on_disk["checks"]["shell.lint"]),
                         (400, "CONFIG_REFUSED", {"enabled": False}),
                         "a value the file may not hold is refused as io.config refuses it")

    def test_a_request_without_the_token_or_from_another_host_is_refused(self):
        cases = {"no token": self.request("GET", "/api/settings")[0],
                 "a wrong token": self.request("GET", "/api/settings", token="guess")[0],
                 "another host name": self.request("GET", "/api/settings", token=self.token,
                                                   host=f"example.com:{self.port}")[0],
                 "a form post": self.request("POST", "/api/setting", b"key=x", token=self.token,
                                             kind="application/x-www-form-urlencoded")[0]}
        self.assertEqual(cases, {"no token": 403, "a wrong token": 403, "another host name": 403,
                                 "a form post": 415},
                         "only the page io.dashboard gave can read or change a setting")

    def test_the_answer_names_the_checks_turned_off(self):
        self.request("POST", "/api/setting", json.dumps({"key": "checks.shell.lint.enabled", "value": False,
                                                        "scope": "project"}).encode(), token=self.token)
        again = dashboard(DashboardInput(), ToolCall(lambda: self.ctx, CancelToken(), self.root, None))
        self.assertEqual(again.checks_off, ("shell.lint",), "the summary names what the project turned off")


if __name__ == "__main__":
    unittest.main()
