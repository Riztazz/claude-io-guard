"""Each fact the package shares is declared once: a constant, a character class, a view of a file's text, this
Python's version, and how an enum reads a value it does not know."""
import inspect
import re
import unittest

from ioguard.checks import command_results, lint
from ioguard.checks.pipeline import Budget
from ioguard.lib.config import GLOBAL_KEYS, defaults
from ioguard.mcp.server import Server
from ioguard.lib import anchors, diagnosis, drift, events, output, profile, rules, text
from ioguard.lib.events import PermissionMode, Tool
from ioguard.lib.platform import detect
from ioguard.lib.probing import Probe, ToolVersion
from tests import PLUGIN_SCRIPTS

PACKAGE = PLUGIN_SCRIPTS / "ioguard"


def lines_matching(pattern: str) -> list[str]:
    """Each line of the package that pattern finds, as module:line."""
    found = re.compile(pattern)
    return [f"{path.relative_to(PACKAGE).as_posix()}:{number}"
            for path in sorted(PACKAGE.rglob("*.py"))
            for number, line in enumerate(path.read_bytes().decode("utf-8").splitlines(), 1)
            if found.search(line)]


class EachConstantIsDeclaredOnce(unittest.TestCase):
    def test_the_bom_character_is_spelled_once(self):
        self.assertEqual(lines_matching(r"chr\(0xFEFF\)"), [f"lib/text.py:{self.declared('BOM_CHAR')}"],
                         "every reader of U+FEFF takes BOM_CHAR from lib.text")

    def test_the_shared_constants_have_one_declaration(self):
        for name in ("PRIVATE_USE", "POWERSHELLS", "PROGRAM_SUFFIXES", "BOM_CHAR"):
            with self.subTest(name=name):
                self.assertEqual(len(lines_matching(rf"^{name}\b.*=")), 1, f"{name} is declared once")

    def test_the_readers_share_one_object(self):
        self.assertIs(profile.PRIVATE_USE, text.PRIVATE_USE, "the profile counts the glyphs text marks")
        self.assertIs(lint.POWERSHELLS, rules.POWERSHELLS, "lint and the rules know the same PowerShells")

    def test_a_character_class_is_built_by_one_function(self):
        self.assertEqual(lines_matching(r"chr\(low\)|chr\(first\)"),
                         [f"lib/text.py:{self.line_of('lib/text.py', 'chr(first)')}"],
                         "output's code page run builds through text.character_class")
        self.assertTrue(output.CODE_PAGE_RUN.fullmatch(chr(0xE9) + chr(0x2019)),
                        "the class still holds a run of the code pages' letters")

    def test_python_reads_stdin_names_the_options_that_take_a_value_once(self):
        self.assertEqual(lines_matching(r'\("-W", "-X"\)|\{"-W", "-X"\}'),
                         [f"lib/shell.py:{self.line_of('lib/shell.py', 'TAKES_VALUE = {')}"],
                         "-W and -X are spelled once, in TAKES_VALUE")

    @staticmethod
    def declared(name: str) -> int:
        return EachConstantIsDeclaredOnce.line_of("lib/text.py", f"{name} = ")

    @staticmethod
    def line_of(module: str, needle: str) -> int:
        lines = (PACKAGE / module).read_bytes().decode("utf-8").splitlines()
        return next(number for number, line in enumerate(lines, 1) if needle in line)


class OneViewOfAFileAsTheEditToolReadsIt(unittest.TestCase):
    def test_the_readers_see_the_same_text(self):
        data = chr(0xFEFF) + "one\r\ntwo\rthree\n"
        self.assertEqual(anchors.file_view(data), "one\ntwo\nthree\n", "no BOM, and every ending as LF")
        self.assertEqual(diagnosis.file_text(data.encode("utf-8")), anchors.file_view(data),
                         "the diagnosis reads the file as the Edit tool does")
        self.assertEqual(drift.edited(data, "two", "2", False).text, "one\n2\nthree\n",
                         "the write comparison applies the edit to the same view")
        self.assertEqual(lines_matching(r'LINE_BREAK\.sub\("\\n"'), [], "no module builds the view by hand")


class EachDefaultIsTheConfigsOwn(unittest.TestCase):
    def test_the_budget_and_the_workers_default_to_their_config_keys(self):
        self.assertEqual(Budget(), Budget.from_config(defaults()), "a bare Budget is the configured one")
        workers = inspect.signature(Server.__init__).parameters["workers"].default
        self.assertEqual(workers, GLOBAL_KEYS["io.server.workers"].default,
                         "a Server built without a worker count takes the config's default")
        self.assertEqual(lines_matching(r"^WORKERS =|soft_ms: int = \d|hard_ms: int = \d"), [],
                         "no second number stands beside the config key")

    def test_the_build_commands_are_declared_once(self):
        lint_builds = set(lint.Lint.meta.config["build_commands"].default)
        result_builds = command_results.CommandResults.meta.config["builds"].default
        self.assertLessEqual(set(result_builds), lint_builds,
                             "every build shell.results knows, shell.lint knows")
        self.assertEqual(len(lines_matching(r'"make", "cmake --build"')), 1,
                         "the builds are one list, which shell.lint extends with its test runners")


class ThisPythonIsMeasuredOnce(unittest.TestCase):
    def test_the_unprobed_python_is_the_measured_one(self):
        self.assertEqual(Probe.unprobed(detect()).python, ToolVersion.this_python(),
                         "the probe and the fallback before it name this Python the same way, stamp and all")


class AnEnumReadsAnUnknownValueOneWay(unittest.TestCase):
    def test_each_enum_falls_back_through_one_helper(self):
        self.assertIs(events.by_value(Tool, "Edit", Tool.OTHER), Tool.EDIT, "a known value is its member")
        self.assertIs(events.by_value(Tool, "mcp__x", Tool.OTHER), Tool.OTHER,
                      "an unknown one is the fallback")
        self.assertIs(events.by_value(Tool, "other", Tool.OTHER), Tool.OTHER, "the fallback's own text too")
        self.assertIs(PermissionMode.named("later"), PermissionMode.UNKNOWN, "a later mode is UNKNOWN")
        self.assertEqual(len(lines_matching(r"for \w+ in cls if \w+\.value == name")), 0,
                         "neither enum spells the lookup itself")


if __name__ == "__main__":
    unittest.main()
