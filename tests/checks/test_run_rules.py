"""run.rules refuses an io.run call a deny rule meets, asks the user about one an ask rule meets, and leaves
every other call alone."""
import json
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.checks.run_rules import RunRules
from ioguard.lib import runs
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeFs
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, callable_name
from tests.support import events

PROJECT = Path("C:/project")
WINDOWS = Platform("win32", True)
SETTINGS = {"permissions": {"deny": ["Bash(git push *)"], "ask": ["Bash(git fetch *)", "Bash(python *)"]}}


def decided(tool_input: dict, tool_name: str = callable_name("io.run")):
    files = {PROJECT / ".claude" / "settings.json": json.dumps(SETTINGS).encode()}
    env = {"CLAUDE_PROJECT_DIR": str(PROJECT), "USERPROFILE": "C:/u"}
    ctx = Context.fake(files, platform=WINDOWS, env=env)
    raw = events.pre_tool_use(tool_name, tool_input, PROJECT)
    registry = Registry()
    registry.register(RunRules)
    return Pipeline(registry).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), ctx), ctx


class AnIoRunCallMeetsTheUsersRules(unittest.TestCase):
    def test_a_deny_rule_refuses_the_call_before_it_runs(self):
        outcome, _ = decided({"argv": ["git", "push", "origin", "main"]})
        result = outcome.decisions[0].results[0]
        self.assertEqual((outcome.verdict, result.code), (Verdict.DENY, Code.RULE_DENIED),
                         "D14: io.run is no way around a Bash deny rule")
        self.assertIn("Bash(git push *)", result.render(), "the refusal names the rule and its file")

    def test_an_ask_rule_asks_and_records_what_it_asked(self):
        for tool_input in ({"argv": ["git", "fetch"]}, {"lang": "python", "code": "print(1)"}):
            with self.subTest(tool_input=tool_input):
                outcome, ctx = decided(tool_input)
                self.assertEqual((outcome.verdict, outcome.decisions[0].results[0].code),
                                 (Verdict.ASK, Code.RULE_ASKED),
                                 "the harness shows its permission prompt, with the rule as the reason")
                kept = {events.TOOL_USE_ID: (runs.key(tool_input), ctx.clock.now())}
                self.assertEqual(ctx.session.asked, kept,
                                 "io.run finds the call the hook put to the user, by its tool use id")

    def test_other_commands_and_other_tools_pass(self):
        for tool_input, tool_name in (({"argv": ["git", "status"]}, callable_name("io.run")),
                                      ({"argv": ["git", "push"]}, callable_name("io.read"))):
            with self.subTest(tool_name=tool_name, tool_input=tool_input):
                self.assertEqual(decided(tool_input, tool_name)[0].verdict, Verdict.OBSERVE,
                                 "a command no rule names, or a call to another tool, says nothing")


if __name__ == "__main__":
    unittest.main()
