"""The io server answers both MCP eras from recorded requests, runs each hook call through the pipeline,
keeps a heartbeat, and answers a cancelled call with CANCELLED."""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.heartbeat import parse
from ioguard.lib.results import Code
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.protocol import Protocol
from ioguard.mcp.server import SAVED, SERVER_INFO, Server, expire
from ioguard.mcp.toolspec import ToolCall, ToolRegistry, ToolSpec
from tests import PLUGIN_SCRIPTS, REPO
from tests.support import injected

SERVER = PLUGIN_SCRIPTS / "ioguard_mcp.py"
INJECT = REPO / "tests" / "support" / "inject"
REQUESTS = Path(__file__).parent / "requests"
SESSION = "s1"


def exchange(lines: list[bytes], data: Path, checks: str = "") -> dict:
    """Send each line, close stdin, and return every answer the server wrote, by its id as text."""
    env = {**os.environ, "IOGUARD_HOME": str(data), "PYTHONPATH": str(INJECT), "IOGUARD_TEST_CHECKS": checks,
           "CLAUDE_CODE_SESSION_ID": SESSION, "CLAUDE_PROJECT_DIR": str(REPO)}
    done = subprocess.run([sys.executable, str(SERVER)], input=b"".join(line + b"\n" for line in lines),
                          capture_output=True, env=env, cwd=REPO, timeout=60)
    answers = [json.loads(line) for line in done.stdout.splitlines()]
    return {json.dumps(answer.get("id")): answer for answer in answers}


def pick(value, path: str):
    """The value at a dotted path. A * takes each item of a list, and a key may hold dots of its own."""
    if not path:
        return value
    if isinstance(value, list):
        head, _, rest = path.partition(".")
        return [pick(item, rest) for item in value] if head == "*" else pick(value[int(head)], rest)
    key = max((key for key in value if path == key or path.startswith(key + ".")), key=len)
    return pick(value[key], path[len(key) + 1:])


def request(number: int, method: str, params: dict) -> bytes:
    return json.dumps({"jsonrpc": "2.0", "id": number, "method": method, "params": params}).encode("ascii")


def hook_call(number: int, command: str, cwd: Path) -> bytes:
    arguments = {"hook_event_name": "PreToolUse", "session_id": SESSION, "tool_name": "Bash", "cwd": str(cwd),
                 "permission_mode": "default", "tool_input": json.dumps({"command": command})}
    return request(number, "tools/call", {"name": "hook.pre_tool_use", "arguments": arguments})


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-server-"))

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)

    def script(self, name: str) -> dict:
        """The answers to a recorded request script, checked against the shapes recorded beside it."""
        answers = exchange((REQUESTS / f"{name}.jsonl").read_bytes().splitlines(), self.data)
        expected = json.loads((REQUESTS / f"{name}.expected.json").read_bytes())
        self.assertEqual(set(answers), set(expected), "each request gets one answer, and a notification none")
        for ident, paths in expected.items():
            for path, value in paths.items():
                with self.subTest(script=name, id=ident, path=path):
                    if path.startswith("!"):
                        parent, field = path[1:].rsplit(".", 1)
                        self.assertNotIn(field, pick(answers[ident], parent), "the answer leaves it out")
                    else:
                        self.assertEqual(pick(answers[ident], path), value, "the answer holds it")
        return answers


class TheServerAnswersBothEras(ServerTest):
    def test_the_legacy_handshake_and_its_calls_answer_as_recorded(self):
        answers = self.script("legacy")
        self.assertEqual(pick(answers["2"], "result.structuredContent.text"), chr(0xFEFF) + "one\r\ntwo\r\n",
                         "io.read keeps the BOM and every CR in the text the model reads")

    def test_the_modern_calls_answer_as_recorded(self):
        self.script("modern")


class TheHookToolsRunThePipeline(ServerTest):
    def test_a_hook_call_with_no_check_answers_an_empty_object_and_records_one_line(self):
        answers = exchange([hook_call(2, "echo hi", self.data)], self.data)
        self.assertEqual(answers["2"]["result"], {"content": [{"type": "text", "text": "{}"}]},
                         "with no check to say anything, the hook tool answers {}, so the tool call goes on")
        lines = [json.loads(line) for path in self.data.rglob(f"{SESSION}.jsonl")
                 for line in path.read_bytes().splitlines()]
        self.assertEqual([(line["event"], line["tool"], line["surface"]) for line in lines],
                         [("PreToolUse", "Bash", "mcp_hook")], "the pipeline records the hook call once")

    def test_a_refusal_comes_back_as_the_tool_text_and_never_as_an_error(self):
        answers = exchange([hook_call(5, f"echo {injected.REFUSE}", self.data)], self.data, "refuse")
        result = answers["5"]["result"]
        decision = json.loads(result["content"][0]["text"])["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny",
                         "the check's refusal reaches Claude Code as a deny in the tool's text")
        self.assertNotIn("isError", result, "a hook tool never sets isError, which would notice every call")

    def test_a_broken_check_warns_once_per_session_across_calls(self):
        answers = exchange([hook_call(6, "echo one", self.data), hook_call(7, "echo two", self.data)],
                           self.data, "broken")
        replies = [json.loads(answers[ident]["result"]["content"][0]["text"]) for ident in ("6", "7")]
        self.assertEqual(sorted("systemMessage" in reply for reply in replies), [False, True],
                         "one server serves the session, so the GUARD_ERROR warning goes out once")


class TheServerKeepsAHeartbeat(ServerTest):
    def test_the_heartbeat_names_the_era_and_a_clean_stop(self):
        exchange([request(0, "initialize", {"protocolVersion": "2025-11-25"})], self.data)
        beat = parse((self.data / "sessions" / f"{SESSION}.alive").read_bytes())
        self.assertEqual((beat.session, beat.era, beat.stopped is not None), (SESSION, "legacy", True),
                         "a server that stopped at the end of stdin says so, so no hook warns about it")


class TheServerDeletesOldTelemetry(unittest.TestCase):
    def test_the_users_retention_decides_which_files_go(self):
        data = Path(tempfile.mkdtemp(prefix="ioguard-retention-"))
        self.addCleanup(shutil.rmtree, data, True)
        now = datetime.now(timezone.utc)
        for name, days in (("old", 31), ("new", 29)):
            path = data / "events" / "2026-01" / f"{name}.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"{}\n")
            stamp = (now - timedelta(days=days)).timestamp()
            os.utime(path, (stamp, stamp))
        config = Config({**defaults().values, "telemetry.retention_days": 30})
        gone = expire(data, lambda: Context.fake(config=config, data_dir=data), now)
        self.assertEqual(([path.stem for path in gone], (data / "events" / "2026-01" / "new.jsonl").exists()),
                         (["old"], True), "a file past the user's 30 days goes, and a newer one stays")

    def test_saved_results_runs_and_bodies_go_after_the_users_days(self):
        data = Path(tempfile.mkdtemp(prefix="ioguard-retention-"))
        self.addCleanup(shutil.rmtree, data, True)
        now = datetime.now(timezone.utc)

        def kept(path: Path, days: int) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"secret\n")
            stamp = (now - timedelta(days=days)).timestamp()
            os.utime(path, (stamp, stamp))
        kept(data / "results" / "old.json", 8)
        kept(data / "results" / "new.json", 6)
        kept(data / "runs" / "old" / "body.py", 8)
        kept(data / "runs" / "old" / "output.log", 9)
        kept(data / "runs" / "live" / "body.py", 30)
        kept(data / "runs" / "live" / "output.log", 0)
        kept(data / "bodies" / "old.sh", 8)

        def left_after(days: int) -> list[str]:
            config = Config({**defaults().values, "io.saved_days": days})
            expire(data, lambda: Context.fake(config=config, data_dir=data), now)
            return sorted(path.relative_to(data).as_posix() for folder in SAVED
                          for path in (data / folder).iterdir())
        self.assertEqual(len(left_after(0)), 5, "0 keeps all five entries")
        self.assertEqual(left_after(7), ["results/new.json", "runs/live"],
                         "an entry whose newest file is past 7 days goes, and a run still writing its log "
                         "stays")


@dataclass(frozen=True)
class Nothing:
    """A tool input with no fields."""


class ACancelledCallAnswersCancelled(unittest.TestCase):
    def test_a_cancel_notification_ends_the_call_with_cancelled(self):
        started = threading.Event()

        def slow(arguments, call):
            started.set()
            call.cancel.event.wait(10)
            return {"content": []}

        tools = ToolRegistry()
        tools.register(ToolSpec("test.slow", "Slow", "Waits for a cancel.", input=Nothing, output=None,
                                read_only=True, destructive=False, idempotent=True, handler=slow))
        protocol = Protocol(tools, SERVER_INFO, lambda cancel: ToolCall(lambda: None, cancel, REPO, None))
        out = io.BytesIO()
        server = Server(protocol, out)
        server.take(request(1, "tools/call", {"name": "test.slow", "arguments": {}}))
        started.wait(10)
        server.take(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled",
                                "params": {"requestId": 1}}).encode("ascii"))
        server.stop()
        answer = json.loads(out.getvalue())
        self.assertEqual((answer["result"]["isError"], answer["result"]["structuredContent"]["code"]),
                         (True, Code.CANCELLED.value), "the call the client cancelled answers CANCELLED")


if __name__ == "__main__":
    unittest.main()
