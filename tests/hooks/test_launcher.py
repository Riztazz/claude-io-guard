"""hook.sh finds a Python that works, skips the Store stub, and warns once when none will do.

hook.py answers every event with at most one JSON object and exits 0.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import PLUGIN_SCRIPTS
from tests.support import events

HOOK_SH = PLUGIN_SCRIPTS / "hook.sh"
HOOK_PY = PLUGIN_SCRIPTS / "hook.py"
SHELL = shutil.which("sh") or shutil.which("bash")
FAKE_PYTHON = b"#!/bin/sh\necho stub-ran\n"
PYTHON_DIR = str(Path(sys.executable).parent)


def data_lines(data: Path) -> list[dict]:
    return [json.loads(line) for path in sorted(data.rglob("*.jsonl"))
            for line in path.read_bytes().splitlines()]


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="ioguard-launcher-"))
        self.data = self.temp / "data"
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("CLAUDE_PLUGIN_")}
        self.env["CLAUDE_PLUGIN_DATA"] = str(self.data)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def fake_python_in(self, folder: str) -> str:
        path = self.temp / folder
        path.mkdir()
        for name in ("python3", "python"):
            (path / name).write_bytes(FAKE_PYTHON)
            (path / name).chmod(0o755)
        return str(path)

    def run_hook_sh(self, event: dict, path: str) -> subprocess.CompletedProcess:
        if SHELL is None:
            self.skipTest("no sh or bash on this machine, so hook.sh cannot run")
        return subprocess.run([SHELL, str(HOOK_SH), "session_start"], input=json.dumps(event).encode("ascii"),
                              capture_output=True, env={**self.env, "PATH": path}, timeout=60)

    def run_hook_py(self, event_name: str, stdin: bytes) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HOOK_PY), event_name], input=stdin,
                              capture_output=True, env=self.env, timeout=60)


class HookShFindsAPython(LauncherTest):
    def test_no_python_on_the_path_gives_one_warning_and_exit_zero(self):
        empty = self.temp / "empty"
        empty.mkdir()
        done = self.run_hook_sh(events.session_start(self.temp), str(empty))
        self.assertEqual(done.returncode, 0, "hook.sh never blocks a session, even with no Python")
        self.assertIn("found no Python", json.loads(done.stdout)["systemMessage"],
                      "with no Python, hook.sh answers with a systemMessage that names the problem")

    def test_the_store_stub_under_windows_apps_is_skipped(self):
        done = self.run_hook_sh(events.session_start(self.temp), self.fake_python_in("WindowsApps"))
        self.assertNotIn(b"stub-ran", done.stdout, "a python under WindowsApps is the Store stub, never run")
        self.assertIn("found no Python", json.loads(done.stdout)["systemMessage"],
                      "with only the Store stub on the path, hook.sh reports no Python found")

    def test_the_same_fake_python_outside_windows_apps_is_run(self):
        done = self.run_hook_sh(events.session_start(self.temp), self.fake_python_in("bin"))
        self.assertIn(b"stub-ran", done.stdout,
                      "hook.sh runs a python3 found outside WindowsApps, so the skip test is not vacuous")

    def test_a_working_python_runs_hook_py_and_records_the_event(self):
        self.env["CLAUDE_PLUGIN_OPTION_PYTHON"] = sys.executable
        done = self.run_hook_sh(events.session_start(self.temp), PYTHON_DIR)
        self.assertEqual((done.returncode, done.stdout), (0, b""),
                         "with a working Python set, session_start answers nothing and exits 0")
        self.assertEqual([line["event"] for line in data_lines(self.data)], ["session_start"],
                         "hook.py recorded the session_start event in the plugin data folder")

    def test_a_server_interpreter_that_does_not_start_python_warns_once(self):
        self.env["CLAUDE_PLUGIN_OPTION_PYTHON"] = "io-guard-no-such-python"
        done = self.run_hook_sh(events.session_start(self.temp), PYTHON_DIR)
        message = json.loads(done.stdout)["systemMessage"]
        self.assertEqual(done.returncode, 0, "a wrong interpreter setting never blocks the session")
        self.assertIn('"io-guard-no-such-python"', message, "the warning names the setting that fails")
        self.assertIn("/plugin configure io-guard", message, "the warning names the fix")


class HookPyAnswers(LauncherTest):
    def bash_event(self) -> bytes:
        return json.dumps(events.bash("echo hi", self.temp)).encode("ascii")

    def test_a_tool_event_gets_no_answer_and_is_recorded(self):
        done = self.run_hook_py("pre_tool_use", self.bash_event())
        self.assertEqual((done.returncode, done.stdout), (0, b""),
                         "hook.py answers a tool event with nothing, so the call goes on")
        self.assertEqual([(line["event"], line["tool"]) for line in data_lines(self.data)],
                         [("pre_tool_use", "Bash")], "hook.py recorded the tool event with its tool")

    def test_stdin_that_is_not_json_still_exits_zero(self):
        done = self.run_hook_py("pre_tool_use", b"{not json")
        self.assertEqual((done.returncode, done.stdout), (0, b""),
                         "hook.py survives a broken event and answers nothing")

    def test_no_plugin_data_folder_records_nothing_and_exits_zero(self):
        del self.env["CLAUDE_PLUGIN_DATA"]
        done = self.run_hook_py("pre_tool_use", self.bash_event())
        self.assertEqual((done.returncode, done.stdout), (0, b""),
                         "without CLAUDE_PLUGIN_DATA hook.py records nothing and still exits 0")


if __name__ == "__main__":
    unittest.main()
