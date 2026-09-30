"""io.run's call reads the same in the hook and in the tool: the argv it runs and the key the hook records."""
import os
import tempfile
import unittest
from pathlib import Path, PureWindowsPath

from ioguard.lib import runs
from ioguard.lib.platform import Platform, detect
from ioguard.lib.probing import Probe, ToolVersion

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
        for program in ("C:/Python314/python.exe", "/bin/bash", "C:/Windows/System32/bash.exe",
                        "/usr/local/bin/bash", "/opt/homebrew/bin/bash"):
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

    def test_a_program_path_lacks_starts_from_git_s_folders_by_its_full_path(self):
        with tempfile.TemporaryDirectory(prefix="ioguard-git-") as folder:
            for name in ("tool", "tool.exe"):
                (Path(folder) / name).write_bytes(b"")
                (Path(folder) / name).chmod(0o755)
            found = runs.start(("tool", "-v"), {"PATH": "", "PATHEXT": ".EXE"}, (folder,))
            missing = runs.start(("absent",), {"PATH": "", "PATHEXT": ".EXE"}, (folder,))
        (argv, env) = found
        self.assertEqual((Path(argv[0]).parent, argv[1:], env["PATH"].split(";")[0], missing),
                         (Path(folder), ("-v",), folder, None),
                         "a program only Git's folders hold runs by its full path with them first on PATH, "
                         "and one they lack too starts nowhere")

    def test_git_s_folders_come_before_path_as_in_the_bash_tool(self):
        with tempfile.TemporaryDirectory(prefix="ioguard-order-") as root:
            windows, git = Path(root) / "System32", Path(root) / "git"
            for folder in (windows, git):
                folder.mkdir()
                for name in ("find", "find.exe"):
                    (folder / name).write_bytes(b"")
                    (folder / name).chmod(0o755)
            env = {"PATH": str(windows), "PATHEXT": ".EXE"}
            found = runs.start(("find", "--version"), env, (str(git),))
            given = runs.start((str(windows / "find.exe"),), env, (str(git),))
        self.assertEqual((Path(found[0][0]).parent, given[0][0]), (git, str(windows / "find.exe")),
                         "a bare name is Git's find before Windows' own, as the Bash tool's shell finds it, "
                         "and a program named by its path runs as named")

    def test_a_body_s_bash_is_never_wsl_s(self):
        with tempfile.TemporaryDirectory(prefix="ioguard-bash-") as root:
            wsl, git = Path(root) / "Windows" / "System32", Path(root) / "Git" / "usr" / "bin"
            for folder in (wsl, git):
                folder.mkdir(parents=True)
                for name in ("bash", "bash.exe"):
                    (folder / name).write_bytes(b"")
                    (folder / name).chmod(0o755)
            env = {"PATH": os.pathsep.join((str(wsl), str(git))), "PATHEXT": ".EXE"}
            found = runs.interpreter("bash", PROBE, WINDOWS, env)
        self.assertEqual(Path(found[0]).parent, git, "with no probed bash, System32's bash.exe, WSL's, is "
                                                     "passed over, as the session probe passes it over")


class EveryProgramIsFoundAsTheBashToolFindsIt(unittest.TestCase):
    def test_the_tool_folders_are_the_probes_bash_s_that_exist_on_windows(self):
        usr = "C:\\Program Files\\Git\\usr\\bin"
        probe = PROBE.__class__(**{**PROBE.__dict__, "bash": ToolVersion(usr + "\\bash.exe", "5.2")})

        def on_disk(folder: Path) -> bool:
            return str(folder) == usr
        found = runs.tool_folders(probe, WINDOWS, on_disk)
        elsewhere = runs.tool_folders(probe, Platform("darwin", True), on_disk)
        self.assertEqual((found, elsewhere), ((usr,), ()),
                         "only the folders the bash's layout has and the disk holds, and none off Windows")

    def test_git_is_found_on_path_then_in_the_tool_folders_then_the_probes(self):
        with tempfile.TemporaryDirectory(prefix="ioguard-git-") as folder:
            for name in ("git", "git.exe"):
                (Path(folder) / name).write_bytes(b"")
                (Path(folder) / name).chmod(0o755)
            probed = PROBE.__class__(**{**PROBE.__dict__, "git": ToolVersion("C:/probed/git.exe", "2.49")})
            none = {"PATH": "", "PATHEXT": ".EXE"}
            found = (runs.git_program(PROBE, {"PATH": folder, "PATHEXT": ".EXE"}, ()),
                     Path(runs.git_program(PROBE, none, (folder,))).parent,
                     runs.git_program(probed, none, ()), runs.git_program(PROBE, none, ()))
        self.assertEqual(found, ("git", Path(folder), "C:/probed/git.exe", "git"),
                         "PATH's git first, then the Bash tool's folders, then the probe's, and git by name "
                         "when nothing holds it, so the start error says so")


if __name__ == "__main__":
    unittest.main()
