"""The tool registry makes each tool's schemas from its dataclasses, lists the tools in order, parses a call's
arguments, and keeps every answer bounded and every bug inside the tool."""
import json
import shutil
import tempfile
import unittest
from dataclasses import dataclass, replace
from pathlib import Path

from ioguard.lib.context import Context, LiveFs
from ioguard.lib.platform import detect
from ioguard.lib.results import Code
from ioguard.lib.telemetry import Telemetry, trace_from
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.protocol import Protocol
from ioguard.mcp.server import registry
from ioguard.mcp.toolspec import NO_DECISION, InvalidArguments, ToolCall, ToolRegistry, ToolSpec, doc, schema

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


@dataclass(frozen=True)
class Inner:
    line: int


@dataclass(frozen=True)
class Given:
    path: str = doc("The file.")
    lines: list[int] = doc("Line numbers.", default_factory=list)
    inner: Inner | None = None
    quiet: bool = False


@dataclass(frozen=True)
class Said:
    text: str

    def render(self) -> str:
        return f"said: {self.text}"


def spec(name: str, handler, given: type | None = Given, said: type | None = Said, **fields) -> ToolSpec:
    return ToolSpec(name, name, "A test tool.", given, said, read_only=True, destructive=False,
                    idempotent=True, handler=handler, **fields)


def call(spill: Path | None = None) -> ToolCall:
    ctx = Context.fake()
    return ToolCall(lambda: ctx, CancelToken(), Path("."), spill)


class SchemasComeFromTheDataclasses(unittest.TestCase):
    def test_an_input_schema_is_strict_and_names_what_is_required(self):
        made = schema(Given, loose=False)
        self.assertEqual((made["required"], made["additionalProperties"], made["properties"]["path"]),
                         (["path"], False, {"type": "string", "description": "The file."}),
                         "a field without a default is required, and an unknown argument is refused")
        self.assertEqual((made["properties"]["lines"], made["properties"]["inner"]["properties"]["line"]),
                         ({"type": "array", "items": {"type": "integer"}, "description": "Line numbers."},
                          {"type": "integer"}), "lists and nested dataclasses become arrays and objects")

    def test_an_output_schema_is_loose(self):
        made = schema(Said, loose=True)
        self.assertEqual((made["additionalProperties"], "required" in made), (True, False),
                         "the client checks structuredContent, so a new field or a saved result passes")

    def test_the_list_keeps_the_registration_order_and_the_annotations(self):
        tools = ToolRegistry()
        for name in ("io.b", "io.a"):
            tools.register(spec(name, lambda given, call: Said("x")))
        listed = tools.list()
        self.assertEqual([entry["name"] for entry in listed], ["io.b", "io.a"], "tools/list keeps one order")
        self.assertEqual(listed[0]["annotations"]["readOnlyHint"], True, "the annotations come from the spec")


class ACallIsParsedAndAnswered(unittest.TestCase):
    def test_arguments_become_the_input_dataclass(self):
        seen = []
        tools = ToolRegistry()
        tools.register(spec("io.echo", lambda given, call: seen.append(given) or Said(given.path)))
        answer = tools.call("io.echo", {"path": "a.txt", "inner": {"line": 3}}, call())
        self.assertEqual((seen[0].inner, answer["content"][0]["text"], answer["structuredContent"]),
                         (Inner(3), "said: a.txt", {"text": "a.txt"}),
                         "the handler gets typed values, and the answer carries the text and the structure")

    def test_arguments_that_do_not_fit_are_refused_by_name(self):
        tools = ToolRegistry()
        tools.register(spec("io.echo", lambda given, call: Said("x")))
        for arguments, said in (({}, "path is required"), ({"path": 3}, "path must be a str"),
                                ({"path": "a", "size": 1}, "size is not an argument"),
                                ({"path": "a", "quiet": 1}, "quiet must be a bool")):
            with self.subTest(arguments=arguments):
                with self.assertRaisesRegex(InvalidArguments, said, msg="the protocol answers -32602"):
                    tools.call("io.echo", arguments, call())

    def test_a_bug_in_a_tool_is_a_guard_error_and_in_a_hook_tool_no_decision(self):
        def broken(given, call):
            raise RuntimeError("bug")
        tools = ToolRegistry()
        tools.register(spec("io.broken", broken))
        tools.register(spec("hook.broken", broken, given=None, said=None))
        answer = tools.call("io.broken", {"path": "a"}, call())
        self.assertEqual((answer["isError"], answer["structuredContent"]["code"]),
                         (True, Code.GUARD_ERROR.value), "a tool's bug is its own error, not the server's")
        self.assertEqual(tools.call("hook.broken", {}, call()), NO_DECISION,
                         "a hook tool's bug lets the guarded call go on, with no hook notice")

    def test_a_result_too_long_for_one_answer_is_saved_and_named(self):
        folder = Path(tempfile.mkdtemp(prefix="ioguard-spill-"))
        self.addCleanup(shutil.rmtree, folder, True)
        tools = ToolRegistry()
        tools.register(spec("io.long", lambda given, call: Said("x" * 200), max_result_chars=100))
        answer = tools.call("io.long", {"path": "a"}, call(folder))
        saved = Path(answer["structuredContent"]["saved"])
        self.assertEqual((saved.read_text(), answer["structuredContent"]["chars"]),
                         ("said: " + "x" * 200, 206), "the whole text goes to a file the answer names")
        self.assertIn("the whole result, 206 characters, is in", answer["content"][0]["text"],
                      "and the text says where it is")


class EachIoToolCallIsOneTelemetryLine(unittest.TestCase):
    """The real registry over a real file, with telemetry written where a session's would be."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ioguard-telemetry-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        (self.root / "a.txt").write_bytes(b"one\r\ntwo\r\n")
        self.ctx = Context.fake(fs=LiveFs(), platform=detect(), data_dir=self.root / "data",
                                telemetry=Telemetry(self.root / "data"))

    def run_call(self, name: str, arguments: dict, cancel: CancelToken | None = None) -> dict:
        given = ToolCall(lambda: self.ctx, cancel or CancelToken(), self.root, None, session="s1",
                         traceparent=TRACEPARENT)
        return registry().call(name, arguments, given)

    def lines(self) -> list[dict]:
        files = sorted((self.root / "data" / "events").rglob("s1.jsonl"))
        return [json.loads(line) for path in files for line in path.read_bytes().splitlines()]

    def test_a_call_records_its_tool_time_extension_and_bytes_and_no_content(self):
        self.run_call("io.edit", {"path": "a.txt", "edits": [{"old_string": "two", "new_string": "SECRET"}]})
        line = self.lines()[0]
        keys = ("session", "surface", "event", "tool", "code", "file_ext", "bytes")
        self.assertEqual({key: line[key] for key in keys},
                         {"session": "s1", "surface": "mcp_tool", "event": "tools/call", "tool": "io.edit",
                          "code": None, "file_ext": ".txt", "bytes": len(b"one\r\nSECRET\r\n")},
                         "section 9's fields, with the bytes the tool wrote")
        self.assertEqual((isinstance(line["latency_ms"], float), line["trace"]["trace_id"],
                          "SECRET" in json.dumps(line)),
                         (True, "4bf92f3577b34da6a3ce929d0e0e4736", False),
                         "the time it took, the caller's trace, and no text of the file or the call")

    def test_a_call_from_a_subfolder_names_the_project_the_hooks_name(self):
        (self.root / "sub").mkdir()
        self.ctx = replace(self.ctx, project=self.root)
        given = ToolCall(lambda: self.ctx, CancelToken(), self.root / "sub", None, session="s1")
        registry().call("io.read", {"path": "../a.txt"}, given)
        self.assertEqual(self.lines()[0]["project"], self.root.name,
                         "the project root's name, as a hook line from the same folder has it")

    def test_a_refused_or_cancelled_call_records_its_code(self):
        self.run_call("io.edit", {"path": "a.txt", "edits": [{"old_string": "absent", "new_string": "x"}]})
        cancel = CancelToken()
        cancel.cancel()
        self.run_call("io.read", {"path": "a.txt"}, cancel)
        self.assertEqual([(line["tool"], line["code"], line["severity"]) for line in self.lines()],
                         [("io.edit", "ANCHOR_NOT_FOUND", "refused"), ("io.read", "CANCELLED", "warning")],
                         "the code the model saw is the code the line holds")

    def test_the_tool_use_id_claude_code_names_joins_the_line_to_its_hooks_trace(self):
        protocol = Protocol(registry(), {"name": "io-guard"},
                            lambda cancel: ToolCall(lambda: self.ctx, cancel, self.root, None, session="s1"))
        meta = {"claudecode/toolUseId": "toolu_01", "progressToken": 1}
        protocol.call({"name": "io.read", "arguments": {"path": "a.txt"}, "_meta": meta}, CancelToken(), None)
        line = self.lines()[0]
        self.assertEqual((line["tool_use_id"], line["trace"]["trace_id"]),
                         ("toolu_01", trace_from("toolu_01", None).trace_id),
                         "row 38: the id the hooks see, and the trace a hook event derives from it")

    def test_a_hook_tool_records_nothing_here(self):
        self.run_call("hook.ping", {})
        self.assertEqual(self.lines(), [], "the pipeline records each hook call itself")

    def test_a_line_that_cannot_be_written_leaves_the_answer_as_it_was(self):
        self.ctx.telemetry.record = lambda event: 1 / 0
        answer = self.run_call("io.read", {"path": "a.txt"})
        self.assertNotIn("isError", answer, "telemetry never fails the call it records")


class ABugIsRecordedWithItsType(unittest.TestCase):
    def test_a_guard_error_line_names_the_exception_type_and_a_hash(self):
        def broken(given, call):
            raise RuntimeError("bug")
        tools = ToolRegistry()
        tools.register(spec("io.broken", broken))
        given = call()
        tools.call("io.broken", {"path": "a"}, given)
        line = given.context.telemetry.events[0]
        self.assertEqual((line.code, line.error.split()[0], len(line.error.split()[1])),
                         (Code.GUARD_ERROR.value, "RuntimeError", 12),
                         "the type and a hash of the traceback, never the traceback")


if __name__ == "__main__":
    unittest.main()
