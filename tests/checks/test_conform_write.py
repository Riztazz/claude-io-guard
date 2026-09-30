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
from tests.support.project import TemporaryProject

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

    def test_a_lone_cr_is_kept_and_named(self):
        for content, expected in (("a\rb\r\nc\nd\n", "a\rb\nc\nd\n"), ("x\ny\rz\n", "x\ny\rz\n")):
            with self.subTest(content=ascii(content)):
                outcome = write(content, {"a.txt": fixture("lf.txt")})
                own = next(decision for decision in outcome.decisions if decision.check_id == "conform.write")
                line = content.replace("\r\n", "\n").split("\r")[0].count("\n") + 1
                self.assertEqual(outcome.tool_input["content"], expected,
                                 "the real endings take the file's style, and the lone CR stays as written")
                self.assertEqual((own.results[0].code, f"lone CR, which ends no line, on line {line}"
                                  in own.results[0].message), (Code.EOL_MISMATCH, True),
                                 "the agent hears of it, rewritten or not, since the Read tool shows it as "
                                 "nothing")

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

    def test_a_new_folder_takes_the_files_of_the_nearest_folder_above(self):
        files = {"Source/Game/a.h": fixture("crlf.txt"), "Source/Game/b.h": fixture("crlf.txt"),
                 "Source/Game/c.cpp": fixture("lf.txt")}
        outcome = write("x\ny\n", files, name="Source/Game/Public/New.h")
        self.assertEqual((outcome.tool_input["content"], [rewrite.note for rewrite in outcome.rewrites]),
                         ("x\r\ny\r\n", ["io-guard wrote the content with CRLF line endings, and a final "
                                         "newline, as the .h files in Source/Game have them."]),
                         "a folder the call creates holds no .h yet, so the nearest folder above with one "
                         "sets the ending, and the note names it")

    def test_a_new_folder_in_a_real_repository_takes_crlf(self):
        with TemporaryProject({"Source/Game/a.h": b"int a;\r\n"}, git=True) as project:
            path = project / "Source" / "Game" / "Public" / "New.h"
            event = Event.from_hook_json(events.write(path, "int b;\n", project), Surface.MCP_HOOK)
            outcome = Pipeline(REGISTRY).run(event, Context.live(None, project, REGISTRY.keys()))
        self.assertEqual(outcome.tool_input["content"], "int b;\r\n",
                         "git finds the root from the nearest folder that exists, and Source/Game's .h sets "
                         "CRLF")

    def test_the_walk_up_stops_at_the_repository_root(self):
        outcome = write("x\ny\n", {"C:/outside.h": fixture("crlf.txt")}, name="Source/New.h")
        self.assertEqual(outcome.rewrites, (), "a file above the repository is another project's, so it sets "
                                               "nothing")

    def test_with_nothing_to_go_on_the_content_stays(self):
        self.assertEqual(write("x\ny\n", {"other.cpp": fixture("crlf.txt")}).rewrites, (),
                         "with no .editorconfig, eol attribute or like sibling, nothing is guessed")


if __name__ == "__main__":
    unittest.main()
