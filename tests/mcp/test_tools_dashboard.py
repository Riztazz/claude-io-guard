"""io.config reads one setting, writes it into the user's or the project's config file as the loader would
accept it, refuses what the file may not hold, and the next hook call runs with it."""
import http.client
import json
import os
import re
import shutil
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from ioguard.checks.registry import Registry, default_registry
from ioguard.hooks import entry
from ioguard.lib.context import Context, LiveFs, project_root
from ioguard.lib.platform import detect
from ioguard.lib.results import Code
from ioguard.lib.telemetry import Telemetry, TelemetryEvent
from ioguard.mcp.dashboard_http import PAGE, Dashboard
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


class YourOwnSettingForOneProject(ConfigTest):
    def test_user_project_turns_a_check_off_in_one_project_and_a_remove_clears_it(self):
        key = "commit_policy.ascii_only"
        with TemporaryProject(git=True) as root, TemporaryProject(git=True) as other:
            self.call(root, key=key, value=True)
            done = self.call(root, key=key, value=False, scope="user_project")
            written = json.loads((self.home / "config.json").read_bytes())
            elsewhere = self.call(other, key=key)
            removed = self.call(root, key=key, scope="user_project", remove=True)
            left = json.loads((self.home / "config.json").read_bytes())
        self.assertEqual((done.applies, elsewhere.applies, written["projects"]),
                         (False, True, {root.as_posix(): {"commit_policy": {"ascii_only": False}}}),
                         "your own entry for a project may turn a check off there, and nowhere else")
        self.assertEqual((removed.applies, left),
                         (True, {"schema": 1, "commit_policy": {"ascii_only": True}}),
                         "a remove takes the entry and projects with it, so All projects applies again")

    def test_a_project_file_refusal_names_the_scope_that_may_loosen(self):
        with TemporaryProject(git=True) as root:
            result = self.refusal(root, key="commit_policy.ascii_only", value=False, scope="project")
        self.assertIn("scope user_project", result.fix.text, "the refusal names the call that works")


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

    def test_a_check_turned_off_for_one_project_stays_on_in_another(self):
        contexts = entry.LiveContexts()
        key = "checks.shell.lint.enabled"
        with TemporaryProject(git=True) as root, TemporaryProject(git=True) as other, \
                mock.patch.dict(os.environ, {"IOGUARD_HOME": str(self.home)}):
            self.call(root, key=key, value=False, scope="user_project")
            here = contexts.get("s1", root, default_registry()).config.get(key)
            there = contexts.get("s2", other, default_registry()).config.get(key)
        self.assertEqual((here, there), (False, True), "a hook call in the project runs without the check")


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

    def test_the_page_is_ascii_loads_nothing_from_outside_and_calls_only_the_api(self):
        page = PAGE.read_bytes()
        calls = sorted(set(re.findall(rb'(?:fetch|post)\("([^"]+)"', page)))
        outside = re.findall(rb"https?://(?!www\.w3\.org/2000/svg\")", page)
        self.assertEqual((page.isascii(), outside, calls),
                         (True, [], [b"/api/ping", b"/api/setting", b"/api/settings", b"/api/stats/delete",
                                     b"/api/stats/from", b"/api/stats?days="]),
                         "one self-contained file, which calls only the paths the server answers, and names "
                         "the SVG namespace alone")

    def test_each_row_carries_your_own_value_for_this_project_apart_from_the_repositorys(self):
        key = "commit_policy.ascii_only"
        for scope, value in (("user", True), ("project", True), ("user_project", False)):
            sent = json.dumps({"key": key, "value": value, "scope": scope}).encode()
            self.request("POST", "/api/setting", sent, token=self.token)
        _, body = self.request("GET", "/api/settings", token=self.token)
        row = next(row for row in json.loads(body)["settings"] if row["key"] == key)
        self.assertEqual({name: row[name] for name in ("user", "project", "own", "applies")},
                         {"user": True, "project": True, "own": False, "applies": False},
                         "your own entry turns the check off here, over the repository's file")

    def test_a_global_key_a_check_reads_sits_under_that_checks_heading(self):
        _, body = self.request("GET", "/api/settings", token=self.token)
        groups = {row["group"] for row in json.loads(body)["settings"] if "commit" in row["key"]}
        self.assertEqual(groups, {"commit.policy"}, "commit_policy's keys join the group of the check")

    def test_the_settings_carry_each_checks_description_for_its_heading(self):
        status, body = self.request("GET", "/api/settings", token=self.token)
        groups = json.loads(body)["groups"]
        self.assertIn("quoting, escaping or dialect", groups["shell.lint"],
                      "a group heading says what it does")

    def test_the_stats_count_this_project_or_every_project_with_each_codes_meaning(self):
        telemetry = Telemetry(self.home)
        now = self.ctx.clock.now()
        for project, code in ((self.root.name, "SHELL_WRITE"), ("other", "PIPE_HIDES_EXIT")):
            telemetry.record(TelemetryEvent(ts=now, session="s1", event="PreToolUse", surface="mcp_hook",
                                            platform="win32", project=project, check="shell.writes",
                                            code=code, severity="refused", cmd_head="sed -i s/a/b/ x"))
        _, own = self.request("GET", "/api/stats?days=7", token=self.token)
        _, every = self.request("GET", "/api/stats?days=7&scope=all", token=self.token)
        own, every = json.loads(own), json.loads(every)
        command = own["recent"]["SHELL_WRITE"][0]["command"]
        self.assertEqual((list(own["codes"]), sorted(every["codes"]), command),
                         (["SHELL_WRITE"], ["PIPE_HIDES_EXIT", "SHELL_WRITE"], "sed -i s/a/b/ x"),
                         "this project's lines alone, or every project's, with the lines behind each code")
        self.assertIn("fix", own["meanings"]["SHELL_WRITE"], "each code comes with its meaning and fix")

    def test_start_from_now_hides_the_lines_before_it_and_show_everything_brings_them_back(self):
        self.record(self.root.name, "SHELL_WRITE")
        self.ctx.clock.advance(1000)
        before = self.counts()
        self.post("/api/stats/from", {"from": "now"})
        hidden = self.counts()
        self.post("/api/stats/from", {"from": None})
        again = self.counts()
        self.assertEqual((before["lines"], hidden["lines"], again["lines"], hidden["stored"]["files"]),
                         (1, 0, 1, 1),
                         "the mark hides the older line and keeps its file, and clearing it shows it again")
        self.assertEqual((hidden["counted_from"] is not None, again["counted_from"]), (True, None),
                         "the page is told where it counts from")

    def test_delete_all_needs_the_confirmation_and_then_deletes_every_projects_file(self):
        self.record(self.root.name, "SHELL_WRITE")
        self.record("other", "PIPE_HIDES_EXIT", session="s2")
        unconfirmed, _ = self.post("/api/stats/delete", {})
        status, body = self.post("/api/stats/delete", {"confirm": True})
        self.assertEqual((unconfirmed, status, json.loads(body), list((self.home / "events").glob("*/*"))),
                         (400, 200, {"deleted": 2, "left": 0}, []),
                         "nothing goes without confirm, and then both projects' files go")

    def post(self, path: str, body: dict) -> tuple[int, bytes]:
        return self.request("POST", path, json.dumps(body).encode(), token=self.token)

    def counts(self) -> dict:
        return json.loads(self.request("GET", "/api/stats?days=7", token=self.token)[1])

    def record(self, project: str, code: str, session: str = "s1") -> None:
        Telemetry(self.home).record(TelemetryEvent(
            ts=self.ctx.clock.now(), session=session, event="PreToolUse", surface="mcp_hook",
            platform="win32", project=project, check="shell.writes", code=code, severity="refused"))

    def test_the_answer_names_the_checks_turned_off(self):
        self.request("POST", "/api/setting", json.dumps({"key": "checks.shell.lint.enabled", "value": False,
                                                        "scope": "project"}).encode(), token=self.token)
        again = dashboard(DashboardInput(), ToolCall(lambda: self.ctx, CancelToken(), self.root, None))
        self.assertEqual(again.checks_off, ("shell.lint",), "the summary names what the project turned off")


class AnUnusedPageServerStops(unittest.TestCase):
    def test_the_idle_time_counts_from_the_last_request(self):
        board = Dashboard({}, {}, idle_s=300)
        board.last = 1000.0
        forever = Dashboard({}, {}, idle_s=0)
        forever.last = 0.0
        self.assertEqual((board.expired(1299.0), board.expired(1300.0), forever.expired(10.0 ** 9)),
                         (False, True, False), "five minutes unasked stops it, and 0 never does")

    def test_a_server_nobody_asks_stops_and_says_so(self):
        stopped = []
        board = Dashboard({}, {}, idle_s=0.05, on_stop=lambda: stopped.append(True))
        self.addCleanup(board.stop)
        board.start()
        deadline = time.monotonic() + 5
        while not stopped and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual((board.server, stopped), (None, [True]), "the server stopped and told its owner")

    def test_the_tool_names_the_idle_stop_and_a_new_call_after_it_starts_again(self):
        home = Path(tempfile.mkdtemp(prefix="ioguard-idle-"))
        self.addCleanup(shutil.rmtree, home, True)
        (home / ".git").mkdir()
        ctx = Context.fake(platform=detect(), fs=LiveFs(), data_dir=home)
        call = ToolCall(lambda: ctx, CancelToken(), home, None)
        first = dashboard(DashboardInput(), call)
        board = BOARDS[project_root(home)]
        board.stop()
        board.on_stop()
        second = dashboard(DashboardInput(), call)
        self.addCleanup(BOARDS.pop(project_root(home)).stop)
        self.assertIn("stops 5 minutes after it closes", first.note, "the model learns the page stops")
        self.assertNotEqual(first.url, second.url, "a new call after the stop opens a new server")


if __name__ == "__main__":
    unittest.main()
