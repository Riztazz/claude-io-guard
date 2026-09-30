"""hooks.entry reads an event, runs the pipeline and answers, and never raises."""
import json
import logging
import os
import unittest
import uuid
from dataclasses import replace
from pathlib import Path
from unittest import mock

from ioguard.checks.registry import Registry, default_registry
from ioguard.hooks import entry
from ioguard.lib.config import Config, ConfigError, LoadReport, defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Decision
from ioguard.lib.events import Event, HookEvent, Surface
from ioguard.lib.platform import detect
from ioguard.lib.probing import Probe, ToolVersion
from tests.support import events, injected
from tests.support.checks import make_check
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

    def test_a_mode_io_guard_does_not_know_gets_defaults_checks_and_one_message(self):
        ctx = Context.fake()
        raw = fresh_session(events.bash(f"echo {injected.ORIGINAL}", CWD, permission_mode="turbo"))
        first = entry.run_event(raw, Surface.COMMAND_HOOK, ctx, registry_of("rewrite"))
        second = entry.run_event(raw, Surface.COMMAND_HOOK, ctx, registry_of("rewrite"))
        self.assertEqual([reply["hookSpecificOutput"]["permissionDecision"] for reply in (first, second)],
                         ["ask", "ask"], "the checks run, under default's rewrite mode, the one that asks")
        self.assertIn("turbo", first.get("systemMessage", ""), "the user hears which mode io-guard met")
        self.assertNotIn("systemMessage", second, "and hears it once a session")

    def test_a_call_the_checks_pass_in_silence_is_confirmed_only_when_the_setting_is_on(self):
        silent = make_check("t.silent", lambda check, event, ctx: Decision.observe("t.silent"),
                            events=(HookEvent.PRE_TOOL_USE, HookEvent.POST_TOOL_USE))
        registry = Registry()
        registry.register(silent)
        on = Config({**defaults().values, "telemetry.confirm": True})
        after = events.post_tool_use("Edit", {"file_path": "a.txt"}, {}, CWD)
        before = events.pre_tool_use("Edit", {"file_path": "a.txt"}, CWD)
        replies = [entry.run_event(raw, Surface.COMMAND_HOOK, Context.fake(config=config), registry)
                   for raw, config in ((after, on), (after, defaults()), (before, on))]
        self.assertEqual(replies[0]["hookSpecificOutput"]["additionalContext"],
                         "io-guard: 1 check ran on this Edit, and none had anything to say.",
                         "with the setting on, a silent call gets one line after it")
        self.assertEqual(replies[1:], [{}, {}], "off by default, and never before the call")
        told = entry.run_event(after, Surface.COMMAND_HOOK, Context.fake(config=on), registry_of("note"))
        self.assertEqual(told["hookSpecificOutput"]["additionalContext"], f"{injected.NOTE} PostToolUse Edit",
                         "a call a check spoke about gets that line alone")

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
                mock.patch.dict(os.environ, {"IOGUARD_HOME": str(data)}):
            one, again = contexts.get("s1", first, Registry()), contexts.get("s1", first, Registry())
            other = contexts.get("s1", second, Registry())
        self.assertIs(one, again, "the config loads once per session and project")
        self.assertIsNot(one, other, "another project loads its own config")
        self.assertIs(one.session, other.session, "the session's state is shared across its projects")

    def test_a_subfolder_gets_its_projects_config_and_a_file_outside_takes_the_users_alone(self):
        config = json.dumps({"checks": {"verify.write": {"ascii_only": [".py"]}}}).encode("ascii")
        with TemporaryProject({".claude/io-guard.json": config, "src/deep/a.py": b"x\n"}) as project, \
                TemporaryProject() as data, mock.patch.dict(os.environ, {"IOGUARD_HOME": str(data)}):
            ctx = entry.LiveContexts().get("s1", project / "src" / "deep", default_registry())
            inside = ctx.for_file(project / "src" / "a.py").config.get("checks.verify.write.ascii_only")
            outside = ctx.for_file(data / "notes.md").config.get("checks.verify.write.ascii_only")
        self.assertEqual((ctx.project, inside, outside), (project, [".py"], []),
                         "the project's layers govern its own files from any subfolder, and no other files")

    def test_the_user_config_comes_from_io_guards_folder(self):
        config = {"transport": {"rewrite_mode": {"default": "refuse"}}}
        with TemporaryProject({"config.json": json.dumps(config).encode("ascii")}) as data, \
                TemporaryProject() as project, mock.patch.dict(os.environ, {"IOGUARD_HOME": str(data)}):
            ctx = entry.LiveContexts().get("s1", project, Registry())
        self.assertEqual(ctx.config.get("transport.rewrite_mode.default"), "refuse",
                         "IOGUARD_HOME names the folder whose config.json is the user layer")

    def test_a_changed_config_file_applies_from_the_next_call_and_keeps_the_session(self):
        contexts, key = entry.LiveContexts(), "transport.rewrite_mode.default"
        with TemporaryProject() as data, TemporaryProject() as project, \
                mock.patch.dict(os.environ, {"IOGUARD_HOME": str(data)}):
            before = contexts.get("s1", project, Registry())
            (data / "config.json").write_bytes(b'{"transport": {"rewrite_mode": {"default": "refuse"}}}')
            after = contexts.get("s1", project, Registry())
            same = contexts.get("s1", project, Registry())
        self.assertEqual((before.config.get(key), after.config.get(key)), ("ask", "refuse"),
                         "a setting written while the server runs applies from the next call")
        self.assertEqual((after.session is before.session, same is after), (True, True),
                         "the session's state survives the rebuild, and an unchanged file builds nothing")

    def test_a_probe_written_after_the_first_call_reaches_the_next(self):
        contexts, bash = entry.LiveContexts(), ToolVersion("C:/Git/usr/bin/bash.exe", "5.2")
        with TemporaryProject() as data, TemporaryProject() as project, \
                mock.patch.dict(os.environ, {"IOGUARD_HOME": str(data)}):
            before = contexts.get("s1", project, Registry())
            probe = replace(Probe.unprobed(detect()), bash=bash)
            (data / "probe.json").write_bytes(json.dumps(probe.to_json()).encode("ascii"))
            after = contexts.get("s1", project, Registry())
        self.assertEqual((before.probe.bash, after.probe.bash, after.session is before.session),
                         (None, bash, True),
                         "the first session's probe, written at its SessionStart, reaches its next hook call")

    def test_a_warning_goes_out_once_across_the_sessions_processes(self):
        with TemporaryProject() as data, TemporaryProject() as project, \
                mock.patch.dict(os.environ, {"IOGUARD_HOME": str(data)}):
            server = entry.LiveContexts().get("s1", project, Registry())
            command_hook = entry.LiveContexts().get("s1", project, Registry())
            said = [server.session.first_time("broken:x"), command_hook.session.first_time("broken:x")]
            again = entry.LiveContexts().get("s2", project, Registry()).session.first_time("broken:x")
        self.assertEqual((said, again), ([True, False], True),
                         "two processes of one session share their warned keys, and another session does not")


if __name__ == "__main__":
    unittest.main()
