"""hooks.bridge reads the maps Claude Code substitutes into an mcp_tool hook, and answers as the tool's text.

tests/fixtures/fields/ holds the maps io-guard's own hooks.json produced live, recorded by the guard-fields
probe on 2026-09-27, and three of task 03's recorded ${tool_input} texts in the same map.
"""
import json
import unittest

from ioguard.checks.registry import Registry
from ioguard.hooks import bridge
from ioguard.lib.context import Context
from ioguard.lib.events import Event, HookEvent, Tool
from tests.support import injected
from tests.support.fixtures import FIXTURES_DIR

FIELDS = FIXTURES_DIR / "fields"


def fields(name: str) -> dict:
    return json.loads((FIELDS / f"{name}.json").read_bytes())


def event(name: str) -> Event:
    return Event.from_fields(fields(name))


def text_of(result: dict) -> dict:
    return json.loads(result["content"][0]["text"])


class TheRecordedMapsDecode(unittest.TestCase):
    def test_every_recorded_map_reads_as_its_event_and_tool(self):
        for path in sorted(FIELDS.glob("*.json")):
            with self.subTest(fixture=path.name):
                read = Event.from_fields(json.loads(path.read_bytes()))
                self.assertTrue(path.stem.startswith(f"{read.kind.name.lower()}_{read.tool_name.lower()}"),
                                "the map reads as the event and tool the fixture is named for")
                self.assertIsNot(read.tool, Tool.OTHER, "every recorded tool is one io-guard guards")

    def test_the_whole_tool_input_keeps_its_types(self):
        self.assertEqual(event("pre_tool_use_bash_timeout").tool_input["timeout"], 60000,
                         "a number inside ${tool_input} stays a number")
        self.assertIs(event("pre_tool_use_edit_replace_all").replace_all, True,
                      "replace_all true arrives as a boolean, which a flat string map loses")
        self.assertIs(event("pre_tool_use_edit").replace_all, False, "and false stays false")

    def test_content_arrives_exact(self):
        content = "say \"hi\"\nC:\\temp\\new\nzazolc with Polish letters: za" + "".join(
            chr(code) for code in (0x17C, 0xF3, 0x142, 0x107))
        self.assertEqual(event("pre_tool_use_write_non_ascii").content, content,
                         "quotes, backslashes, newlines and non-ASCII survive the substitution")

    def test_tool_response_and_error_arrive(self):
        self.assertEqual(event("post_tool_use_bash").tool_response["stdout"], "hi",
                         "${tool_response} arrives whole as JSON text, and decodes to Bash's output object")
        self.assertEqual(event("post_tool_use_failure_bash").error, "Exit code 3",
                         "${error} arrives as the failure's text")
        self.assertIs(event("post_tool_use_failure_read").kind, HookEvent.POST_TOOL_USE_FAILURE,
                      "a failed Read reads as PostToolUseFailure")

    def test_an_empty_value_is_absent(self):
        read = event("pre_tool_use_bash")
        self.assertEqual((read.agent_id, read.tool_response), (None, None),
                         "an empty agent_id and a missing tool_response are both absent")


class TheBridgeAnswersAsText(unittest.TestCase):
    def test_every_recorded_map_answers_an_empty_object_with_no_check(self):
        for path in sorted(FIELDS.glob("*.json")):
            with self.subTest(fixture=path.name):
                result = bridge.call(json.loads(path.read_bytes()), Context.fake(), Registry())
                self.assertEqual(result, {"content": [{"type": "text", "text": "{}"}]},
                                 "with no check the tool's text is {}, and the call goes on")

    def test_a_refusal_is_the_tools_text_and_never_an_error(self):
        registry = Registry()
        registry.register(injected.CHECKS["refuse"])
        mapped = {**fields("pre_tool_use_bash"),
                  "tool_input": json.dumps({"command": f"echo {injected.REFUSE}"})}
        result = bridge.call(mapped, Context.fake(), registry)
        self.assertEqual(text_of(result)["hookSpecificOutput"]["permissionDecision"], "deny",
                         "the deny travels in the text, where Claude Code reads it")
        self.assertNotIn("isError", result, "a hook tool never sets isError")

    def test_a_map_that_is_not_an_event_answers_an_empty_object(self):
        with self.assertLogs("ioguard.hooks"):
            result = bridge.call({**fields("pre_tool_use_bash"), "tool_input": "{not json"}, Context.fake())
        self.assertEqual(text_of(result), {}, "a map io-guard cannot read lets the call go on")


if __name__ == "__main__":
    unittest.main()
