"""The stub io server answers the legacy handshake and records each hook call without deciding anything."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import PLUGIN_SCRIPTS

SERVER = PLUGIN_SCRIPTS / "server.py"


def exchange(requests: list, data: Path) -> list[dict]:
    """Send each request as one line, close stdin, and return every answer the server wrote."""
    encoded = [item if isinstance(item, bytes) else json.dumps(item).encode("ascii") for item in requests]
    lines = b"".join(line + b"\n" for line in encoded)
    env = {**os.environ, "IOGUARD_DATA": str(data)}
    done = subprocess.run([sys.executable, str(SERVER)], input=lines, capture_output=True, env=env,
                          timeout=60)
    return [json.loads(line) for line in done.stdout.splitlines()]


def request(number: int, method: str, params: dict | None = None) -> dict:
    return {"jsonrpc": "2.0", "id": number, "method": method, "params": params or {}}


class StubServerAnswersTheLaunch(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-server-"))

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def test_the_legacy_handshake_echoes_the_client_version_and_lists_the_hook_tool(self):
        answers = exchange([request(0, "initialize", {"protocolVersion": "2025-11-25"}),
                            {"jsonrpc": "2.0", "method": "notifications/initialized"},
                            request(1, "tools/list")], self.data)
        self.assertEqual(answers[0]["result"]["protocolVersion"], "2025-11-25",
                         "initialize answers with the client's protocol version")
        self.assertEqual([tool["name"] for tool in answers[1]["result"]["tools"]], ["hook.pre_tool_use"],
                         "tools/list offers the one hook tool and nothing the model would call")

    def test_a_hook_call_returns_no_decision_and_records_one_line(self):
        arguments = {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Bash",
                     "tool_input": "{\"command\":\"echo hi\"}"}
        answers = exchange([request(2, "tools/call", {"name": "hook.pre_tool_use", "arguments": arguments})],
                           self.data)
        self.assertEqual(answers[0]["result"], {"content": [{"type": "text", "text": ""}]},
                         "a hook call answers with empty text, which lets the tool call go on")
        lines = [json.loads(line) for path in self.data.rglob("s1.jsonl")
                 for line in path.read_bytes().splitlines()]
        self.assertEqual([(line["event"], line["tool"], line["surface"]) for line in lines],
                         [("PreToolUse", "Bash", "mcp_hook")],
                         "the hook call is recorded once, in its session's file")

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
