"""hooks.entry reads an event, runs the pipeline and answers, and never raises."""
import json
import logging
import os
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest import mock

from ioguard.checks.registry import Registry
from ioguard.hooks import entry
from ioguard.lib.config import Config, ConfigError, LoadReport, defaults
from ioguard.lib.context import Context
from ioguard.lib.events import Event, Surface
from tests.support import events, injected
from tests.support.fixtures import FIXTURES_DIR
from tests.support.project import TemporaryProject

CWD = Path.cwd()


def registry_of(*names: str) -> Registry:
    registry = Registry()
    for name in names:
        registry.register(injected.CHECKS[name])
    return registry


def fresh_session(raw: dict) -> dict:
    """The event in a session no other test has used, so a once-per-session warning is this test's own."""
    return {**raw, "session_id": str(uuid.uuid4())}


class RunEventAnswersAndNeverRaises(unittest.TestCase):
    def test_every_recorded_event_answers_through_an_empty_registry(self):
        for path in sorted((FIXTURES_DIR / "events").glob("*.json")):
            with self.subTest(event=path.name):
                raw = json.loads(path.read_bytes())
                self.assertEqual(entry.run_event(raw, Surface.COMMAND_HOOK, Context.fake(), Registry()), {},
                                 "a recorded event reads, runs and answers {} with no check")

    def test_an_event_it_cannot_read_answers_an_empty_object_and_logs_guard_error(self):
        with self.assertLogs("ioguard.hooks", logging.WARNING) as logged:
            reply = entry.run_event({"hook_event_name": "PreToolUse"}, Surface.COMMAND_HOOK, Context.fake())
        self.assertEqual(reply, {}, "an event with no session or cwd answers {}")
        self.assertIn("GUARD_ERROR", logged.output[0], "the unreadable event is logged as GUARD_ERROR")

    def test_a_failure_past_the_pipeline_warns_the_session_once(self):
        broken = replace(Context.fake(), config=Config({}))    # no pipeline keys, so the budget cannot load
        raw = fresh_session(events.bash("echo hi", CWD))
        with self.assertLogs("ioguard.hooks", logging.ERROR):
            first = entry.run_event(raw, Surface.COMMAND_HOOK, broken, Registry())
            second = entry.run_event(raw, Surface.COMMAND_HOOK, broken, Registry())
        self.assertTrue(first["systemMessage"].startswith("GUARD_ERROR:"), "the first failure tells the user")
        self.assertEqual(second, {}, "the second failure in the session answers {} without a warning")

    def test_the_rewrite_mode_comes_from_the_events_permission_mode(self):
        for mode, decision in (("auto", "deny"), ("default", "ask"), ("bypassPermissions", "allow")):
            with self.subTest(permission_mode=mode):
                raw = events.bash(f"echo {injected.ORIGINAL}", CWD, permission_mode=mode)
                reply = entry.run_event(raw, Surface.COMMAND_HOOK, Context.fake(), registry_of("rewrite"))
                self.assertEqual(reply["hookSpecificOutput"]["permissionDecision"], decision,
                                 f"the default rewrite mode for {mode} answers {decision}")

    def test_a_config_error_is_named_once_per_session(self):
        error = ConfigError(Path("io-guard.json"), "chekcs", "io-guard has no such key.", "checks")
        report = LoadReport(defaults(), (error,), (), (Path("io-guard.json"),))
        ctx = Context.fake(config_report=report)
        raw = events.bash("echo hi", CWD)
        first = entry.run_event(raw, Surface.COMMAND_HOOK, ctx, Registry())
        second = entry.run_event(raw, Surface.COMMAND_HOOK, ctx, Registry())
        self.assertIn("chekcs", first["systemMessage"], "the first answer names the bad key")
        self.assertEqual(second, {}, "later answers in the session stay quiet about it")

    def test_an_mcp_hook_map_reads_through_from_fields(self):
        fields = {"hook_event_name": "PreToolUse", "session_id": "s", "cwd": str(CWD), "tool_name": "Bash",
                  "permission_mode": "", "tool_input": json.dumps({"command": f"echo {injected.REFUSE}"})}
        reply = entry.run_event(fields, Surface.MCP_HOOK, Context.fake(), registry_of("refuse"))
        self.assertEqual(reply["hookSpecificOutput"]["permissionDecision"], "deny",
                         "the substituted map decodes into the same event a command hook reads")


class LiveContextsKeepOneSessionState(unittest.TestCase):
    def test_a_session_gets_one_context_per_project_and_one_state_across_them(self):
        contexts = entry.LiveContexts()

        with TemporaryProject() as first, TemporaryProject() as second, TemporaryProject() as data, \
                mock.patch.dict(os.environ, {"IOGUARD_DATA": str(data)}):
            one, again = contexts.get("s1", first, Registry()), contexts.get("s1", first, Registry())
            other = contexts.get("s1", second, Registry())
        self.assertIs(one, again, "the config loads once per session and project")
        self.assertIsNot(one, other, "another project loads its own config")
        self.assertIs(one.session, other.session, "the session's state is shared across its projects")

    def test_the_user_config_comes_from_the_data_folder(self):
        config = {"transport": {"rewrite_mode": {"default": "refuse"}}}
        with TemporaryProject({"config.json": json.dumps(config).encode("ascii")}) as data, \
                TemporaryProject() as project, mock.patch.dict(os.environ, {"IOGUARD_DATA": str(data)}):
            ctx = entry.LiveContexts().get("s1", project, Registry())
        self.assertEqual(ctx.config.get("transport.rewrite_mode.default"), "refuse",
                         "IOGUARD_DATA names the folder whose config.json is the user layer")

    def test_a_warning_goes_out_once_across_the_sessions_processes(self):
        with TemporaryProject() as data, TemporaryProject() as project, \
                mock.patch.dict(os.environ, {"IOGUARD_DATA": str(data)}):
            server = entry.LiveContexts().get("s1", project, Registry())
            command_hook = entry.LiveContexts().get("s1", project, Registry())
            said = [server.session.first_time("broken:x"), command_hook.session.first_time("broken:x")]
            again = entry.LiveContexts().get("s2", project, Registry()).session.first_time("broken:x")
        self.assertEqual((said, again), ([True, False], True),
                         "two processes of one session share their warned keys, and another session does not")


if __name__ == "__main__":
    unittest.main()
