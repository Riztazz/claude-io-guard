"""proc.run starts a program from a list, only from where PATH holds it when it is named without a folder,
and a timeout or a missing program is a result, not a raise."""
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from ioguard.lib import proc

HERE = Path(__file__).parent


class ProgramsRun(unittest.TestCase):
    def test_a_program_gives_its_exit_code_and_output(self):
        result = proc.run([sys.executable, "-c", "import sys; sys.stdout.write('hi'); sys.exit(3)"], HERE)
        self.assertEqual((result.exit_code, result.stdout, result.ok), (3, b"hi", False),
                         "run returns the exit code and the raw output")

    def test_an_argument_with_quotes_and_spaces_arrives_whole(self):
        tricky = 'say "hi" and $HOME `x` C:\\temp\\new'
        result = proc.run([sys.executable, "-c", "import sys; sys.stdout.write(sys.argv[1])", tricky], HERE)
        self.assertEqual(result.stdout.decode("utf-8"), tricky, "no shell re-reads an argument")

    def test_stdin_carries_the_given_bytes_and_nothing_of_the_callers(self):
        echo = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"]
        given = proc.run(echo, HERE, stdin=b"a\r\nb\n")
        empty = proc.run(echo, HERE, timeout_s=5)
        self.assertEqual((given.stdout, empty.stdout, empty.timed_out), (b"a\r\nb\n", b"", False),
                         "a program reads the bytes it is given, and without any it reads an ended stdin, "
                         "never the io server's messages")

    def test_a_timeout_is_a_result(self):
        result = proc.run([sys.executable, "-c", "import time; time.sleep(5)"], HERE, timeout_s=0.3)
        self.assertEqual((result.timed_out, result.exit_code), (True, None), "a timeout ends the wait")

    def test_a_background_program_logs_its_output_and_tells_when_it_ends(self):
        log = Path(tempfile.mkdtemp(prefix="ioguard-proc-")) / "out" / "run.log"
        self.addCleanup(shutil.rmtree, log.parent.parent, True)
        ended = threading.Event()
        pump = proc.background([sys.executable, "-c", "import sys; print('out', flush=True); "
                                "print('err', file=sys.stderr); sys.exit(4)"], HERE, os.environ, log)
        pump.when_done(ended.set)
        self.assertTrue(pump.wait(30) and ended.wait(5), "the waiter thread sees the end and calls back")
        self.assertEqual((pump.exit_code, log.read_bytes().split()), (4, [b"out", b"err"]),
                         "stdout and stderr share one log, and the exit code is kept")
        called = []
        pump.when_done(lambda: called.append(True))
        self.assertEqual(called, [True], "a callback after the end runs at once")

    def test_stopping_a_background_program_ends_what_it_started(self):
        log = Path(tempfile.mkdtemp(prefix="ioguard-proc-")) / "run.log"
        self.addCleanup(shutil.rmtree, log.parent, True)
        child = "import subprocess, sys, time; subprocess.Popen([sys.executable, '-c', 'import time; " \
                "time.sleep(60)']); print('started', flush=True); time.sleep(60)"
        pump = proc.background([sys.executable, "-c", child], HERE, os.environ, log)
        started = time.monotonic()
        while b"started" not in log.read_bytes() and time.monotonic() - started < 30:
            pump.wait(0.05)
        pump.stop()
        self.assertTrue(pump.done.is_set(), "stop waits for the program to end")

    def test_a_missing_program_is_a_result(self):
        result = proc.run(["io-guard-no-such-program"], HERE)
        self.assertEqual((result.exit_code, result.ok), (None, False), "a missing program is not ok")
        self.assertTrue(result.start_error, "the result says why the program did not start")


class OnlyAProgramOnThePathStarts(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ioguard-path-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.name = "tool.exe" if sys.platform == "win32" else "tool"

    def planted(self, folder: str) -> Path:
        path = self.root / folder / self.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
        path.chmod(0o755)
        return path

    def test_a_folder_named_in_skip_is_passed_over(self):
        for folder in ("WindowsApps", "git/usr/bin"):
            self.planted(folder)
        folders = [self.root / "WindowsApps", self.root / "git" / "usr" / "bin"]
        env = {"PATH": os.pathsep.join(map(str, folders))}
        found = proc.on_path("tool", env, skip=("windowsapps",))
        first = proc.on_path("tool", env)
        self.assertEqual(Path(found).parent.name, "bin", "the skipped folder is passed over, ignoring case")
        self.assertEqual(Path(first).parent.name, "WindowsApps", "and without skip the first folder wins")

    def test_an_empty_path_entry_never_means_the_current_folder(self):
        self.planted("repo")
        previous = Path.cwd()
        os.chdir(self.root / "repo")
        self.addCleanup(os.chdir, previous)
        self.assertIsNone(proc.on_path("tool", {"PATH": os.pathsep + str(self.root / "empty")}),
                          "an empty entry is skipped, where the operating system reads the current folder")

    def test_a_bare_name_path_lacks_never_starts_from_the_folder_it_runs_in(self):
        self.planted("repo")
        result = proc.run(["tool", "--version"], self.root / "repo", {"PATH": str(self.root / "empty")})
        with self.assertRaises(FileNotFoundError):
            proc.background(["tool"], self.root / "repo", {"PATH": ""}, self.root / "log.txt")
        refused = "tool is not on PATH, so io-guard did not start it."
        self.assertEqual((result.exit_code, result.start_error), (None, refused),
                         "a program the repository ships is never run in place of one PATH lacks")

    def test_a_program_given_as_a_path_runs_as_given(self):
        self.assertEqual(proc.located([sys.executable, "-V"], {"PATH": ""}), (sys.executable, "-V"),
                         "a path needs no PATH")


if __name__ == "__main__":
    unittest.main()
