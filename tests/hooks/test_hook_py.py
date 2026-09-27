"""hook.py, run as Claude Code runs it, answers each recorded event with the documented JSON.

Each test starts hook.py as a subprocess on an event from tests/fixtures/events/, with the test checks from
tests/support/injected.py installed through tests/support/inject, so the plugin runs as shipped.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import PLUGIN_SCRIPTS, REPO
from tests.support import injected
from tests.support.fixtures import FIXTURES_DIR

HOOK_PY = PLUGIN_SCRIPTS / "hook.py"
INJECT = REPO / "tests" / "support" / "inject"
RECORDED = {
    "PreToolUse": "pre_tool_use_bash.json",
    "PostToolUse": "post_tool_use_bash.json",
    "PostToolUseFailure": "post_tool_use_failure_read.json",
    "SessionStart": "session_start.json",
}


def recorded(event_name: str) -> dict:
    return json.loads((FIXTURES_DIR / "events" / RECORDED[event_name]).read_bytes())


class HookPyTest(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-hookpy-"))
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("CLAUDE_PLUGIN_")}
        self.env.update(CLAUDE_PLUGIN_DATA=str(self.data), CLAUDE_PLUGIN_OPTION_PYTHON=sys.executable,
                        PYTHONPATH=str(INJECT))

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def hook(self, event: dict, checks: str = "", argument: str = "tool_event") -> dict:
        """Run hook.py on the event with the named test checks, and return its one JSON answer."""
        done = subprocess.run([sys.executable, str(HOOK_PY), argument],
                              input=json.dumps(event).encode("ascii"), capture_output=True,
                              env={**self.env, "IOGUARD_TEST_CHECKS": checks}, timeout=60)
        self.assertEqual(done.returncode, 0, f"hook.py always exits 0: {done.stderr!r}")
        self.assertTrue(done.stdout.isascii(), "hook.py writes ASCII only")
        return json.loads(done.stdout)

    def bash(self, command: str, permission_mode: str = "default") -> dict:
        event = recorded("PreToolUse")
        return {**event, "permission_mode": permission_mode, "tool_input": {**event["tool_input"],
                                                                            "command": command}}

    def set_mode(self, mode: str) -> None:
        config = {"transport": {"rewrite_mode": {"default": mode}}}
        (self.data / "config.json").write_bytes(json.dumps(config).encode("ascii"))


class EveryEventGetsItsAnswer(HookPyTest):
    def test_with_nothing_to_say_every_recorded_event_answers_an_empty_object(self):
        for event_name in ("PreToolUse", "PostToolUse", "SessionStart"):
            with self.subTest(event=event_name):
                self.assertEqual(self.hook(recorded(event_name)), {},
                                 "with nothing to say, the answer is {} and the call goes on")

    def test_the_recorded_missing_read_gets_its_diagnosis(self):
        reply = self.hook(recorded("PostToolUseFailure"))["hookSpecificOutput"]
        self.assertTrue(reply["additionalContext"].startswith("PATH_NOT_FOUND: "),
                        "a Read of a missing file is answered with the paths that exist")

    def test_every_recorded_event_carries_the_checks_context_under_its_own_name(self):
        for event_name in RECORDED:
            with self.subTest(event=event_name):
                reply = self.hook(recorded(event_name), checks="note")
                self.assertEqual(reply["hookSpecificOutput"]["hookEventName"], event_name,
                                 "the answer names the event it answers")
                self.assertIn(injected.NOTE, reply["hookSpecificOutput"]["additionalContext"],
                              "the check's line reaches the model as additionalContext")

    def test_a_post_tool_use_answer_carries_the_replaced_output_and_the_classifier_note(self):
        reply = self.hook(recorded("PostToolUse"), checks="output")["hookSpecificOutput"]
        self.assertEqual(reply["updatedToolOutput"], {**recorded("PostToolUse")["tool_response"],
                                                      "stdout": injected.OUTPUT},
                         "updatedToolOutput keeps Bash's own output shape, with stdout replaced")
        self.assertEqual(reply["classifierContext"], injected.CLASSIFIER,
                         "the classifier note goes out as classifierContext")

    def test_a_refusal_answers_deny_with_the_rendered_result_as_the_reason(self):
        reply = self.hook(self.bash(f"echo {injected.REFUSE}"), checks="refuse")["hookSpecificOutput"]
        self.assertEqual(reply["permissionDecision"], "deny", "a refusing check denies the call")
        self.assertIn("Run echo IOGUARD_ALLOWED instead.", reply["permissionDecisionReason"],
                      "the reason is the rendered result, ending with its fix")

    def test_a_broken_check_answers_the_other_checks_and_warns_the_user(self):
        reply = self.hook(recorded("PreToolUse"), checks="broken,note")
        self.assertIn(injected.NOTE, reply["hookSpecificOutput"]["additionalContext"],
                      "the checks after the broken one still ran")
        self.assertTrue(reply["systemMessage"].startswith("GUARD_ERROR:"),
                        "the user hears of the broken check")

    def test_an_event_io_guard_cannot_read_answers_an_empty_object(self):
        event = {**recorded("PreToolUse"), "permission_mode": "no-such-mode"}
        self.assertEqual(self.hook(event, checks="note"), {},
                         "an event io-guard cannot read answers {}, and the call goes on")


class EveryRewriteModeShapesTheAnswer(HookPyTest):
    def rewritten(self, mode: str) -> dict:
        self.set_mode(mode)
        return self.hook(self.bash(f"echo {injected.ORIGINAL}"), checks="rewrite")["hookSpecificOutput"]

    def test_refuse_denies_and_the_reason_carries_the_rewritten_command(self):
        reply = self.rewritten("refuse")
        self.assertEqual(reply["permissionDecision"], "deny", "refuse mode denies the rewritten call")
        self.assertIn(f"Run this command instead, exactly as written:\necho {injected.REWRITTEN}",
                      reply["permissionDecisionReason"], "the model reruns the corrected command")
        self.assertNotIn("updatedInput", reply, "a refusal changes nothing itself")

    def test_ask_shows_the_rewritten_input_with_the_note(self):
        reply = self.rewritten("ask")
        self.assertEqual((reply["permissionDecision"], reply["updatedInput"]["command"]),
                         ("ask", f"echo {injected.REWRITTEN}"),
                         "ask mode shows the user the corrected command")
        self.assertIn("rewrote the command", reply["permissionDecisionReason"],
                      "the prompt carries the rewrite's note")

    def test_allow_runs_the_rewritten_input_and_tells_the_model(self):
        reply = self.rewritten("allow")
        self.assertEqual((reply["permissionDecision"], reply["updatedInput"]["command"]),
                         ("allow", f"echo {injected.REWRITTEN}"), "allow mode runs the corrected command")
        self.assertIn("rewrote the command", reply["additionalContext"], "the model hears of the rewrite")

    def test_the_mode_follows_the_events_permission_mode(self):
        reply = self.hook(self.bash(f"echo {injected.ORIGINAL}", "bypassPermissions"), checks="rewrite")
        self.assertEqual(reply["hookSpecificOutput"]["permissionDecision"], "allow",
                         "bypassPermissions defaults to allow while default mode defaults to ask")


if __name__ == "__main__":
    unittest.main()
