"""io.run's call reads the same in the hook and in the tool: the argv it runs and the key the hook records."""
import tempfile
import unittest
from pathlib import Path, PureWindowsPath

from ioguard.lib import runs
from ioguard.lib.context import Probe, ToolVersion
from ioguard.lib.platform import Platform, detect

WINDOWS = Platform("win32", True)
PROBE = Probe.unprobed(WINDOWS)


class ACallNamesOneCommand(unittest.TestCase):
    def test_argv_runs_as_given_and_a_body_runs_through_its_interpreter(self):
        python = ToolVersion("C:/Python314/python.exe", "3.14")
        probe = PROBE.__class__(**{**PROBE.__dict__, "python": python})
        self.assertEqual(runs.argv_of({"argv": ["git", "status"]}, probe, WINDOWS, {}), ("git", "status"),
                         "an argv runs as the call gives it")
        self.assertEqual(runs.argv_of({"lang": "python", "code": "1"}, probe, WINDOWS, {}, "C:/r/body.py"),
                         ("C:/Python314/python.exe", "C:/r/body.py"),
                         "a body runs through the probe's Python")
        self.assertIsNone(runs.argv_of({"lang": "cobol", "code": "1"}, probe, WINDOWS, {}),
                          "a language with no interpreter runs nothing")

    def test_an_interpreter_comes_from_the_environment_the_call_is_given(self):
        with tempfile.TemporaryDirectory(prefix="ioguard-path-") as folder:
            for name in ("node", "node.exe"):
                (Path(folder) / name).write_bytes(b"")
                (Path(folder) / name).chmod(0o755)
            env = {"PATH": folder, "PATHEXT": ".EXE"}
            found = runs.argv_of({"lang": "node", "code": "1"}, PROBE, detect(), env, "body.js")
        self.assertEqual((Path(found[0]).parent, found[1:]), (Path(folder), ("body.js",)),
                         "the interpreter is the one on the given PATH, never the process's")

    def test_the_key_tells_calls_apart_by_what_they_run(self):
        keys = {runs.key({"argv": ["git", "fetch"]}), runs.key({"argv": ["git", "fetch", "-v"]}),
                runs.key({"lang": "python", "code": "a"}), runs.key({"lang": "python", "code": "b"})}
        self.assertEqual(len(keys), 4, "each command, and each body, has its own key")


class GitBashGetsItsOwnTools(unittest.TestCase):
    GIT = PureWindowsPath("C:/Program Files/Git")
    TOOLS = (str(GIT / "mingw64" / "bin"), str(GIT / "usr" / "local" / "bin"), str(GIT / "usr" / "bin"))

    def test_git_bash_by_either_path_names_git_s_tool_folders(self):
        for program in ("C:/Program Files/Git/usr/bin/bash.EXE", "C:\\Program Files\\Git\\bin\\bash.exe"):
            with self.subTest(program=program):
                self.assertEqual(runs.git_tools(program), self.TOOLS,
                                 "the folders Git's own login shell puts first, in its order")
        for program in ("C:/Python314/python.exe", "/bin/bash", "C:/Windows/System32/bash.exe"):
            with self.subTest(program=program):
                self.assertEqual(runs.git_tools(program), (), "any other program changes nothing")

    def test_the_tools_go_first_on_path_whatever_its_key_is_called(self):
        bash = "C:/Program Files/Git/usr/bin/bash.exe"
        found = runs.with_git_tools({"Path": "C:\\Windows", "X": "1"}, bash)
        self.assertEqual(found,
                         {"Path": ";".join((*self.TOOLS, "C:\\Windows")), "X": "1", "MSYSTEM": "MINGW64"},
                         "Git's tools come before the rest of PATH, and MSYSTEM is set as the Bash tool "
                         "sets it")
        kept = runs.with_git_tools({"PATH": "C:\\a", "MSYSTEM": "UCRT64"}, bash)
        self.assertEqual(kept["MSYSTEM"], "UCRT64", "an MSYSTEM the environment names stays")
        same = {"PATH": "C:\\a"}
        self.assertEqual(runs.with_git_tools(same, "C:/Python314/python.exe"), same,
                         "another program's run is left as it is")


if __name__ == "__main__":
    unittest.main()
