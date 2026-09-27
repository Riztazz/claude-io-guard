"""The stub io server answers the legacy handshake and runs each hook call through the bridge."""
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

SERVER = PLUGIN_SCRIPTS / "server.py"
INJECT = REPO / "tests" / "support" / "inject"


def exchange(requests: list, data: Path, checks: str = "") -> list[dict]:
    """Send each request as one line, close stdin, and return every answer the server wrote. checks names
    the test checks the server runs with."""
    encoded = [item if isinstance(item, bytes) else json.dumps(item).encode("ascii") for item in requests]
    lines = b"".join(line + b"\n" for line in encoded)
    env = {**os.environ, "IOGUARD_DATA": str(data), "PYTHONPATH": str(INJECT), "IOGUARD_TEST_CHECKS": checks}
    done = subprocess.run([sys.executable, str(SERVER)], input=lines, capture_output=True, env=env,
                          timeout=60)
    return [json.loads(line) for line in done.stdout.splitlines()]


def hook_call(number: int, command: str, cwd: Path) -> dict:
    arguments = {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Bash", "cwd": str(cwd),
                 "permission_mode": "default", "tool_input": json.dumps({"command": command})}
    return request(number, "tools/call", {"name": "hook.pre_tool_use", "arguments": arguments})


def request(number: int, method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": number, "method": method, "params": params or {}}


class StubServerAnswersTheLaunch(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-server-"))

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def test_the_legacy_handshake_echoes_the_client_version_and_lists_the_hook_tools(self):
        answers = exchange([request(0, "initialize", {"protocolVersion": "2025-11-25"}),
                            {"jsonrpc": "2.0", "method": "notifications/initialized"},
                            request(1, "tools/list")], self.data)
        self.assertEqual(answers[0]["result"]["protocolVersion"], "2025-11-25",
                         "initialize answers with the client's protocol version")
        self.assertEqual([tool["name"] for tool in answers[1]["result"]["tools"]],
                         ["hook.pre_tool_use", "hook.post_tool_use", "hook.post_tool_use_failure"],
                         "tools/list offers the three hook tools and nothing the model would call")

    def test_a_hook_call_with_no_check_answers_an_empty_object_and_records_one_line(self):
        answers = exchange([hook_call(2, "echo hi", self.data)], self.data)
        self.assertEqual(answers[0]["result"], {"content": [{"type": "text", "text": "{}"}]},
                         "with no check to say anything, the hook tool answers {}, so the tool call goes on")
        lines = [json.loads(line) for path in self.data.rglob("s1.jsonl")
                 for line in path.read_bytes().splitlines()]
        self.assertEqual([(line["event"], line["tool"], line["surface"]) for line in lines],
                         [("PreToolUse", "Bash", "mcp_hook")],
                         "the pipeline records the hook call once, in its session's file")

    def test_a_refusal_comes_back_as_the_tool_text_and_never_as_an_error(self):
        answers = exchange([hook_call(5, f"echo {injected.REFUSE}", self.data)], self.data, checks="refuse")
        result = answers[0]["result"]
        decision = json.loads(result["content"][0]["text"])["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny",
                         "the check's refusal reaches Claude Code as a deny in the tool's text")
        self.assertNotIn("isError", result, "a hook tool never sets isError, which would notice every call")

    def test_a_broken_check_warns_once_per_session_across_calls(self):
        answers = exchange([hook_call(6, "echo one", self.data), hook_call(7, "echo two", self.data)],
                           self.data, checks="broken")
        replies = [json.loads(answer["result"]["content"][0]["text"]) for answer in answers]
        self.assertEqual(["systemMessage" in reply for reply in replies], [True, False],
                         "one server serves the session, so the GUARD_ERROR warning goes out once")

    def test_an_unknown_method_is_a_method_not_found_error(self):
        answers = exchange([request(3, "server/discover")], self.data)
        self.assertEqual(answers[0]["error"]["code"], -32601,
                         "a method the stub lacks is a JSON-RPC method-not-found error")

    def test_a_line_that_is_not_json_is_skipped_and_the_server_goes_on(self):
        answers = exchange([b"{not json", request(4, "ping")], self.data)
        self.assertEqual(answers, [{"jsonrpc": "2.0", "id": 4, "result": {}}],
                         "the server skips a broken line and still answers the next request")


if __name__ == "__main__":
    unittest.main()
