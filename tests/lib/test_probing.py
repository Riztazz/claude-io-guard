"""lib.probing measures tools, versions and names without deciding anything, and keeps an unchanged tool's
version without running it again."""
import os
import re
import unittest
from pathlib import Path

from ioguard.lib import probing
from ioguard.lib.context import ToolVersion
from ioguard.lib.platform import detect
from ioguard.lib.proc import RunResult
from tests.support.project import TemporaryProject

PATTERN = re.compile(r"version (\d+\.\d+\.\d+)")


class Runner:
    """A stand-in for proc.run that answers with fixed output and counts its calls."""

    def __init__(self, stdout: bytes, exit_code: int = 0) -> None:
        self.stdout, self.exit_code, self.calls = stdout, exit_code, []

    def __call__(self, argv, cwd, timeout_s=10.0) -> RunResult:
        self.calls.append((tuple(argv), cwd))
        return RunResult(tuple(argv), self.exit_code, self.stdout, b"", False, 0.01)


class AToolVersionIsMeasuredOnce(unittest.TestCase):
    def test_the_version_is_read_from_the_output_and_stamped(self):
        with TemporaryProject({"bin/tool": b"x"}) as root:
            path = str(root / "bin" / "tool")
            runner = Runner(b"GNU bash, version 5.2.37(1)-release\n")
            found = probing.tool_version(path, PATTERN, run=runner)
        self.assertEqual((found.path, found.version), (path, "5.2.37"), "the version is the pattern's group")
        self.assertIsNotNone(found.stamp, "the file's size and mtime are kept with it")
        self.assertEqual(runner.calls, [((path, "--version"), root / "bin")],
                         "the tool runs with --version in its own folder, never the project's")

    def test_an_unchanged_tool_keeps_its_previous_version_without_running(self):
        with TemporaryProject({"tool": b"x"}) as root:
            path = str(root / "tool")
            previous = ToolVersion(path, "1.0.0", probing.stamp(path))
            runner = Runner(b"version 9.9.9")
            found = probing.tool_version(path, PATTERN, previous, run=runner)
        self.assertEqual((found, runner.calls), (previous, []), "a stamp that still matches skips the run")

    def test_a_changed_tool_is_measured_again(self):
        with TemporaryProject({"tool": b"x"}) as root:
            path = str(root / "tool")
            previous = ToolVersion(path, "1.0.0", "1:1")
            found = probing.tool_version(path, PATTERN, previous, run=Runner(b"version 2.0.0"))
        self.assertEqual(found.version, "2.0.0", "a different size or mtime means a new measure")

    def test_a_tool_that_fails_or_prints_no_version_has_none(self):
        with TemporaryProject({"tool": b"x"}) as root:
            path = str(root / "tool")
            self.assertIsNone(probing.tool_version(path, PATTERN, run=Runner(b"version 1.2.3", exit_code=1)),
                              "a failing tool has no version")
            self.assertIsNone(probing.tool_version(path, PATTERN, run=Runner(b"no numbers")),
                              "output with no version has none, never a guess")


class TheClaudeCodeVersion(unittest.TestCase):
    def test_it_comes_from_the_agent_variable_first(self):
        env = {"AI_AGENT": "claude-code_2-1-281_agent", "CLAUDE_CODE_EXECPATH": "C:/x/2.1.999/claude.exe"}
        self.assertEqual(probing.claude_version(env), "2.1.281", "AI_AGENT names the running release")

    def test_then_from_the_executables_folder(self):
        env = {"CLAUDE_CODE_EXECPATH": "C:\\Users\\u\\AppData\\Roaming\\Claude\\claude-code\\2.1.283\\"
                                       "claude.exe"}
        self.assertEqual(probing.claude_version(env), "2.1.283", "the bundled binary's folder names it")

    def test_an_environment_naming_none_gives_none(self):
        self.assertIsNone(probing.claude_version({}), "no variable means no version, never a guess")

    def test_versions_compare_as_numbers(self):
        self.assertLess(probing.version_tuple("2.1.99"), probing.version_tuple("2.1.281"),
                        "2.1.99 comes before 2.1.281, which a string comparison gets wrong")


class TheMachine(unittest.TestCase):
    def test_case_matches_the_platforms_default_file_system(self):
        with TemporaryProject() as root:
            self.assertEqual(probing.case_insensitive(root, False), detect().case_insensitive,
                             "a temp folder's case rule is the platform's default")

    def test_a_name_with_no_letters_gives_the_default(self):
        self.assertIs(probing.case_insensitive(Path("123"), True), True,
                      "nothing to swap, so the default holds")

    def test_the_console_encoding_is_named(self):
        self.assertTrue(probing.console_encoding(), "the encoding a piped Python prints through has a name")

    def test_this_python_is_stamped(self):
        python = probing.this_python()
        self.assertEqual((python.version.split(".")[0], python.stamp is not None), ("3", True),
                         "the running Python is measured with its stamp")


if __name__ == "__main__":
    unittest.main()
