"""conform.write writes new content in the file's own endings, BOM and final newline, and takes a new file's
convention from .editorconfig, .gitattributes and its siblings."""
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeGit
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code
from tests.support import events
from tests.support.fixtures import FIXTURES_DIR

CWD = Path("C:/project")
TARGET = CWD / "a.txt"
WINDOWS = Platform("win32", True)
REGISTRY = default_registry()
BOM = b"\xef\xbb\xbf"


def write(content: str, files: dict | None = None, attributes: dict | None = None, name: str = "a.txt"):
    event = Event.from_hook_json(events.write(CWD / name, content, CWD), Surface.MCP_HOOK, WINDOWS)
    git = FakeGit(root=CWD, attributes={event.file_path: attributes or {}})
    ctx = Context.fake(files={CWD / key: value for key, value in (files or {}).items()},
                       config=defaults(REGISTRY.keys()), platform=WINDOWS, git=git)
    return Pipeline(REGISTRY).run(event, ctx)


def fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


class AnExistingFileKeepsItsConvention(unittest.TestCase):
    def test_every_fixture_gets_its_own_endings_and_bom(self):
        cases = {"crlf.txt": "x\r\ny\r\n", "lf.txt": "x\ny\n", "bom-crlf.txt": chr(0xFEFF) + "x\r\ny\r\n",
                 "bom-lf.txt": chr(0xFEFF) + "x\ny\n",
                 "no-final-newline.txt": "x\ny", "lone-cr.txt": "x\r\ny\r\n"}
        for name, expected in cases.items():
            with self.subTest(fixture=name):
                outcome = write("x\ny\n", {"a.txt": fixture(name)})
                self.assertEqual(outcome.tool_input["content"], expected,
                                 "the content takes the file's ending, its BOM and its final-newline rule")

    def test_the_code_names_what_changed(self):
        endings = write("x\ny\n", {"a.txt": fixture("crlf.txt")}).rewrites[0].code
        bom_only = write("x\ny\n", {"a.txt": fixture("bom-lf.txt")}).rewrites[0].code
        self.assertEqual((endings, bom_only), (Code.EOL_CONVERTED, Code.BOM_RESTORED),
                         "a changed ending is EOL_CONVERTED, and a BOM alone is BOM_RESTORED")

    def test_a_mixed_file_keeps_the_content_with_a_warning(self):
        outcome = write("x\ny\n", {"a.txt": fixture("mixed.txt")})
        own = next(decision for decision in outcome.decisions if decision.check_id == "conform.write")
        self.assertEqual((outcome.rewrites, own.results[0].code), ((), Code.EOL_MISMATCH),
                         "no one ending is the file's own, so nothing is guessed")

    def test_binary_empty_and_matching_files_are_left_alone(self):
        for name, content in (("nul-byte.txt", "x\n"), ("lf.txt", "x\ny\n")):
            with self.subTest(fixture=name):
                self.assertEqual(write(content, {"a.txt": fixture(name)}).rewrites, (),
                                 "a binary file, or content already in the file's convention, is left alone")

    def test_conformed_content_is_a_fixed_point(self):
        first = write("x\ny\n", {"a.txt": fixture("bom-crlf.txt")}).tool_input["content"]
        again = write(first, {"a.txt": fixture("bom-crlf.txt")})
        self.assertEqual((again.verdict, again.rewrites), (Verdict.OBSERVE, ()),
                         "conformed input stays as it is")


class ANewFileTakesTheConventionAroundIt(unittest.TestCase):
    def test_editorconfig_decides_first(self):
        editorconfig = b"root = true\n[*.txt]\nend_of_line = crlf\ncharset = utf-8-bom\n"
        outcome = write("x\ny\n", {".editorconfig": editorconfig, "b.txt": fixture("lf.txt")})
        self.assertEqual(outcome.tool_input["content"], chr(0xFEFF) + "x\r\ny\r\n",
                         ".editorconfig's end_of_line and charset outrank the sibling")

    def test_gitattributes_then_siblings(self):
        by_attribute = write("x\ny\n", attributes={"eol": "crlf"}).tool_input["content"]
        by_siblings = write("x\ny\n", {"b.txt": fixture("crlf.txt"), "c.txt": fixture("crlf.txt"),
                                       "d.cpp": fixture("lf.txt")}).tool_input["content"]
        self.assertEqual((by_attribute, by_siblings), ("x\r\ny\r\n", "x\r\ny\r\n"),
                         "eol from .gitattributes, else most siblings with the same extension")

    def test_with_nothing_to_go_on_the_content_stays(self):
        self.assertEqual(write("x\ny\n", {"other.cpp": fixture("crlf.txt")}).rewrites, (),
                         "with no .editorconfig, eol attribute or like sibling, nothing is guessed")


if __name__ == "__main__":
    unittest.main()
