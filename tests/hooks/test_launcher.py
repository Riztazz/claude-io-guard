"""pyrun and pyrun.cmd start one Python for the io server and the command hooks, and name the fix when they
cannot.

IOGUARD_PYTHON names the interpreter. Without it, Windows tries py -3, then python, and macOS python3, then
python. hook.py answers every event with one JSON object and exits 0. test_hook_py covers what the answer
holds.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import PLUGIN_SCRIPTS
from tests.support import events

PYRUN = PLUGIN_SCRIPTS / "pyrun"
PYRUN_CMD = PLUGIN_SCRIPTS / "pyrun.cmd"
HOOK_PY = PLUGIN_SCRIPTS / "hook.py"
SHELL = shutil.which("sh") or shutil.which("bash")
PYTHON_DIR = str(Path(sys.executable).parent)
WINDOWS = os.name == "nt"


def data_lines(data: Path) -> list[dict]:
    return [json.loads(line) for path in sorted(data.rglob("*.jsonl"))
            for line in path.read_bytes().splitlines()]


def load_hook_py():
    spec = importlib.util.spec_from_file_location("ioguard_hook_py", HOOK_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="ioguard-launcher-"))
        self.data = self.temp / "data"
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("CLAUDE_PLUGIN_") and key not in ("IOGUARD_PYTHON", "OS")}
        self.env["CLAUDE_PLUGIN_DATA"] = str(self.data)

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)


class PyrunUnderSh(LauncherTest):
    """pyrun, the way a command hook runs it on Windows under Git Bash and on macOS under sh."""

    def setUp(self):
        super().setUp()
        if SHELL is None:
            self.skipTest("no sh or bash on this machine, so pyrun cannot run")

    def fakes(self, *names: str) -> str:
        """A folder holding a fake interpreter per name, each printing its name and its arguments."""
        folder = self.temp / "bin"
        folder.mkdir(exist_ok=True)
        for name in names:
            (folder / name).write_bytes(f'#!/bin/sh\necho {name} "$@"\n'.encode("ascii"))
            (folder / name).chmod(0o755)
        return str(folder)

    def pyrun(self, path: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run([SHELL, str(PYRUN), "script.py", "a", "b"], capture_output=True, timeout=60,
                              env={**self.env, "PATH": path, **env})

    def test_ioguard_python_runs_the_interpreter_it_names(self):
        named = Path(self.fakes("named")) / "named"
        done = self.pyrun(self.fakes("python3", "python"), IOGUARD_PYTHON=named.as_posix())
        self.assertEqual(done.stdout.split(), [b"named", b"script.py", b"a", b"b"],
                         "IOGUARD_PYTHON wins over every name on PATH, and the arguments pass through")

    def test_an_ioguard_python_that_is_no_program_is_named_and_exits_one(self):
        done = self.pyrun(self.fakes("python3"), IOGUARD_PYTHON="/no/such/python")
        self.assertEqual((done.returncode, done.stdout), (1, b""), "a wrong IOGUARD_PYTHON starts nothing")
        self.assertIn(b"IOGUARD_PYTHON is /no/such/python", done.stderr, "the message quotes the value")

    def test_windows_runs_the_py_launcher_with_dash_3_first(self):
        done = self.pyrun(self.fakes("py", "python3", "python"), OS="Windows_NT")
        self.assertEqual(done.stdout.split(), [b"py", b"-3", b"script.py", b"a", b"b"],
                         "on Windows the launcher python.org installs runs first, asked for Python 3")

    def test_windows_without_py_runs_python_and_never_python3(self):
        done = self.pyrun(self.fakes("python3", "python"), OS="Windows_NT")
        self.assertEqual(done.stdout.split()[0], b"python",
                         "on Windows python3 is not tried, since pyrun.cmd does not try it either")

    def test_elsewhere_python3_runs_first_and_py_is_not_tried(self):
        done = self.pyrun(self.fakes("py", "python3", "python"))
        self.assertEqual(done.stdout.split()[0], b"python3", "on macOS python3 runs before python")

    def test_elsewhere_python_runs_when_python3_is_missing(self):
        done = self.pyrun(self.fakes("python"))
        self.assertEqual(done.stdout.split()[0], b"python", "python is the last name tried")

    def test_no_python_names_the_fix_and_exits_one(self):
        done = self.pyrun(self.fakes())
        self.assertEqual((done.returncode, done.stdout), (1, b""), "with no Python, pyrun starts nothing")
        self.assertIn(b"found no Python", done.stderr, "the message names the problem")
        self.assertIn(b"IOGUARD_PYTHON", done.stderr, "the message names the variable that fixes it")

    def test_a_working_python_runs_hook_py_and_records_the_event(self):
        done = subprocess.run([SHELL, str(PYRUN), str(HOOK_PY), "session_start"],
                              input=json.dumps(events.session_start(self.temp)).encode("ascii"),
                              capture_output=True, timeout=60,
                              env={**self.env, "PATH": PYTHON_DIR, "IOGUARD_PYTHON": sys.executable})
        self.assertEqual((done.returncode, done.stdout), (0, b"{}"),
                         "session_start on a working Python answers an empty object and exits 0")
        self.assertEqual([line["event"] for line in data_lines(self.data)], ["SessionStart"],
                         "the pipeline recorded the SessionStart event in the plugin data folder")


@unittest.skipUnless(WINDOWS, "pyrun.cmd is for cmd.exe, on Windows")
class PyrunCmd(LauncherTest):
    """pyrun.cmd, the way Claude Code starts the io server on Windows."""

    def fakes(self, *names: str) -> str:
        """PATH with a folder holding a fake interpreter per name, and System32 for where.exe."""
        folder = self.temp / "bin"
        folder.mkdir(exist_ok=True)
        for name in names:
            (folder / f"{name}.cmd").write_bytes(f"@echo {name} %*\r\n".encode("ascii"))
        return os.pathsep.join([str(folder), str(Path(os.environ["SystemRoot"]) / "System32")])

    def pyrun(self, path: str, cwd: Path | None = None, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run([str(PYRUN_CMD), "script.py", "a", "b"], capture_output=True, timeout=60,
                              cwd=cwd or self.temp, env={**self.env, "PATH": path, **env})

    def test_pyrun_cmd_keeps_crlf_line_endings(self):
        data = PYRUN_CMD.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"),
                         "cmd.exe finds goto labels reliably only in a CRLF file")

    def test_pyrun_cmd_runs_the_ioguard_python_it_names(self):
        path = self.fakes("python")
        done = self.pyrun(path, IOGUARD_PYTHON=str(self.temp / "bin" / "python.cmd"))
        self.assertEqual(done.stdout.split(), [b"python", b"script.py", b"a", b"b"],
                         "IOGUARD_PYTHON as a full path runs that file with the arguments")

    def test_pyrun_cmd_names_an_ioguard_python_that_is_no_program(self):
        wrong = "C:/Program Files (x86)/no such/python.exe"
        done = self.pyrun(self.fakes("py"), IOGUARD_PYTHON=wrong)
        self.assertEqual((done.returncode, done.stdout), (1, b""), "a wrong IOGUARD_PYTHON starts nothing")
        self.assertIn(f"IOGUARD_PYTHON is {wrong}".encode("ascii"), done.stderr,
                      "the message quotes the value, parentheses included")

    def test_pyrun_cmd_runs_the_py_launcher_first_with_dash_3(self):
        done = self.pyrun(self.fakes("py", "python"))
        self.assertEqual(done.stdout.split(), [b"py", b"-3", b"script.py", b"a", b"b"],
                         "the launcher python.org installs runs first, asked for Python 3")

    def test_pyrun_cmd_runs_python_without_py(self):
        done = self.pyrun(self.fakes("python"))
        self.assertEqual(done.stdout.split()[0], b"python", "python runs when there is no py launcher")

    def test_pyrun_cmd_with_no_python_names_the_fix_and_exits_one(self):
        done = self.pyrun(self.fakes())
        self.assertEqual((done.returncode, done.stdout), (1, b""), "with no Python, pyrun.cmd starts nothing")
        self.assertIn(b"found no Python", done.stderr, "the message names the problem")

    def test_pyrun_cmd_never_runs_a_python_in_the_project_folder(self):
        project = self.temp / "project"
        project.mkdir()
        for name in ("py", "python"):
            (project / f"{name}.cmd").write_bytes(b"@echo planted\r\n")
        done = self.pyrun(self.fakes(), cwd=project)
        self.assertNotIn(b"planted", done.stdout,
                         "a py or python in the folder the server starts in never runs")
        self.assertIn(b"found no Python", done.stderr, "pyrun.cmd looks on PATH only")

    def test_pyrun_cmd_passes_arguments_with_spaces_whole(self):
        script = self.temp / "show.py"
        script.write_bytes(b"import json, sys\nprint(json.dumps(sys.argv[1:]))\n")
        done = subprocess.run([str(PYRUN_CMD), str(script), "one arg", "two"], capture_output=True,
                              timeout=60, env={**self.env, "IOGUARD_PYTHON": sys.executable})
        self.assertEqual(json.loads(done.stdout), ["one arg", "two"],
                         "stdout carries only the script's output, with each argument whole")


class HookPyWarns(unittest.TestCase):
    def test_python_3_14_or_later_gets_no_warning(self):
        self.assertIsNone(load_hook_py().interpreter_warning(), "this suite runs on 3.14 or later")

    def test_an_older_python_is_named_with_the_fix(self):
        hook_py = load_hook_py()
        with mock.patch.object(hook_py.sys, "version_info", (3, 13, 2, "final", 0)):
            warning = hook_py.interpreter_warning()
        self.assertIn(f"{sys.executable} is 3.13.2", warning, "the warning names the interpreter and version")
        self.assertIn("IOGUARD_PYTHON", warning, "the warning names the variable that fixes it")


class HookPyAnswers(LauncherTest):
    def run_hook_py(self, event_name: str, stdin: bytes) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HOOK_PY), event_name], input=stdin,
                              capture_output=True, env=self.env, timeout=60)

    def bash_event(self) -> bytes:
        return json.dumps(events.bash("echo hi", self.temp)).encode("ascii")

    def test_a_tool_event_gets_an_empty_answer_and_is_recorded(self):
        done = self.run_hook_py("pre_tool_use", self.bash_event())
        self.assertEqual((done.returncode, done.stdout), (0, b"{}"),
                         "with no check to say anything, hook.py answers {}, so the call goes on")
        self.assertEqual([(line["event"], line["tool"]) for line in data_lines(self.data)],
                         [("PreToolUse", "Bash")], "the pipeline recorded the tool event with its tool")

    def test_stdin_that_is_not_json_still_exits_zero(self):
        done = self.run_hook_py("pre_tool_use", b"{not json")
        self.assertEqual((done.returncode, done.stdout), (0, b"{}"),
                         "hook.py survives a broken event and answers {}")
        self.assertIn(b"GUARD_ERROR", done.stderr, "the crash before the answer is logged as GUARD_ERROR")

    def test_no_plugin_data_folder_records_nothing_and_exits_zero(self):
        del self.env["CLAUDE_PLUGIN_DATA"]
        done = self.run_hook_py("pre_tool_use", self.bash_event())
        self.assertEqual((done.returncode, done.stdout), (0, b"{}"),
                         "without CLAUDE_PLUGIN_DATA hook.py keeps telemetry in memory and still answers")


if __name__ == "__main__":
    unittest.main()
