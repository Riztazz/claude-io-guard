"""io.edit, io.splice and io.append change a file in memory and write it once, in the file's own bytes. They
do what the scratchpad helpers agents wrote did, refuse a batch whole, and take turns on one file."""
import hashlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest import mock

from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context, LiveFs
from ioguard.lib.fakes import FakeFs
from ioguard.lib.platform import Platform, detect
from ioguard.lib.results import Code, Severity, callable_name
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_edit import NOTE, AppendInput, EditInput, EditPair, SpliceInput, append, edit, splice
from ioguard.mcp.toolspec import ToolCall, ToolFailure
from tests import PLUGIN_SCRIPTS
from tests.support.fixtures import FIXTURES_DIR

CWD = Path("C:/project")
WINDOWS = Platform("win32", True)
EDIT = callable_name("io.edit")
DAY = "2026-09-27"                 # the fake clock's day
CHILD = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from ioguard.lib.context import Context, LiveFs
from ioguard.lib.platform import detect
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_edit import EditInput, EditPair, edit
from ioguard.mcp.toolspec import ToolCall
target, data, key, rounds = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], int(sys.argv[5])
ctx = Context.fake(fs=LiveFs(), data_dir=data, platform=detect())
print("ready", flush=True)
sys.stdin.readline()
for step in range(rounds):
    pair = EditPair(f"{key}={step}\\n", f"{key}={step + 1}\\n")
    edit(EditInput(str(target), (pair,)), ToolCall(lambda: ctx, CancelToken(), target.parent, None))
"""


def baseline_edit(data: bytes, pairs: list[tuple[str, str]]) -> bytes:
    """The scratchpad edit() most agents wrote: the text read with newline='', each LF in a pair written as
    the file's ending, one match asserted per pair, the pairs made in order, and one write."""
    text = data.decode("utf-8")
    ending = "\r\n" if "\r\n" in text else "\n"
    for old, new in pairs:
        old, new = old.replace("\n", ending), new.replace("\n", ending)
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    return text.encode("utf-8")


def baseline_tlog(data: bytes, entry: str) -> bytes:
    """tlog.py: a bullet, the day and the entry, wrapped at 116 with the lines after the first indented 2,
    after the file's last line break, in the file's endings."""
    text = data.decode("utf-8")
    ending = "\r\n" if "\r\n" in text else "\n"
    lines = textwrap.wrap(f"- {DAY} - {entry}", 116, subsequent_indent="  ")
    return (text.rstrip("\n") + "\n" + ending.join(lines) + ending).encode("utf-8")


def fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


class EditTest(unittest.TestCase):
    """A test with its own plugin data folder, which holds the lock files."""

    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-edit-"))
        self.addCleanup(shutil.rmtree, self.data, True)

    def context(self, files: dict, **options) -> Context:
        values = {**defaults().values, **{f"io.edit.{name}": value for name, value in options.items()}}
        return Context.fake(config=Config(MappingProxyType(values)), platform=WINDOWS, fs=FakeFs(files),
                            data_dir=self.data)

    def run_tool(self, handler, given, ctx: Context, cwd: Path = CWD):
        return handler(given, ToolCall(lambda: ctx, CancelToken(), cwd, None))

    def refusal(self, handler, given, ctx: Context):
        with self.assertRaises(ToolFailure) as failure:
            self.run_tool(handler, given, ctx)
        self.assertEqual(ctx.fs.writes, [], "a refused call writes nothing")
        return failure.exception.result

    def edited(self, data: bytes, *pairs: tuple[str, str], **given) -> tuple[bytes, object]:
        ctx = self.context({CWD / "a.txt": data})
        batch = tuple(EditPair(*pair) for pair in pairs)
        found = self.run_tool(edit, EditInput("a.txt", batch, **given), ctx)
        return ctx.fs.files[CWD / "a.txt"], found


class TheBaselineHelpersAreReproduced(EditTest):
    def test_a_batch_lands_as_the_baseline_edit_helper_left_it(self):
        pairs = [("one\n", "zero\none\n"), ("two", "TWO\ntwo and a half")]
        for name in ("crlf.txt", "lf.txt", "bom-crlf.txt", "bom-lf.txt"):
            with self.subTest(fixture=name):
                written, _ = self.edited(fixture(name), *pairs)
                self.assertEqual(written, baseline_edit(fixture(name), pairs),
                                 "the file's endings and BOM, byte for byte as the helper wrote them")

    def test_an_append_lands_as_tlog_left_it(self):
        entry = "Task 24 lands the batch edit, the splice between two markers and the dated append. " * 3
        for data in (b"# Log\r\n- earlier\r\n", b"# Log\n- earlier\n"):
            with self.subTest(data=data):
                ctx = self.context({CWD / "log.md": data})
                self.run_tool(append, AppendInput("log.md", f"- {entry.strip()}", 116, True), ctx)
                self.assertEqual(ctx.fs.files[CWD / "log.md"], baseline_tlog(data, entry.strip()),
                                 "the dated entry, wrapped at 116 and hung under its words")


class TheFileKeepsItsBytes(EditTest):
    def test_lines_the_edit_leaves_keep_their_own_endings(self):
        for name, pair, expected in (
                ("mixed.txt", ("three", "3"), b"one\r\ntwo\n3\r\nfour\n"),
                ("mixed.txt", ("two", "two\nhalf"), b"one\r\ntwo\r\nhalf\nthree\r\nfour\n"),
                ("lone-cr.txt", ("three", "3"), b"one\r\ntwo\r3\r\n")):
            with self.subTest(fixture=name, pair=pair):
                self.assertEqual(self.edited(fixture(name), pair)[0], expected,
                                 "untouched endings stay, and a new line takes the ending most lines use")

    def test_a_code_page_file_and_a_utf16_file_keep_their_encoding(self):
        cp1250 = fixture("cp1250.txt")
        self.assertEqual(self.edited(cp1250, ("za", "ZA"))[0], cp1250.replace(b"za", b"ZA", 1),
                         "a cp1250 file stays cp1250, every byte outside the edit unchanged")
        utf16 = (chr(0xFEFF) + "one\r\ntwo\r\n").encode("utf-16-le")
        expected = (chr(0xFEFF) + "one\r\n2\r\n").encode("utf-16-le")
        self.assertEqual(self.edited(utf16, ("two", "2"))[0], expected,
                         "a UTF-16 file keeps its BOM and its two bytes a character")

    def test_new_text_takes_the_indent_around_it(self):
        written, found = self.edited(b"void f()\n{\n\tone();\n\ttwo();\n}\n",
                                     ("\ttwo();", "    two();\n    three();"))
        note = "io-guard indented the new_string of edit 1 with tabs, as the lines around it are."
        expected = b"void f()\n{\n\tone();\n\ttwo();\n\tthree();\n}\n"
        self.assertEqual((written, found.indented), (expected, [note]),
                         "spaces beside tab-indented lines become tabs, and the result says so")

    def test_the_result_names_the_lines_the_hash_and_the_fresh_read(self):
        written, found = self.edited(b"a\nb\nc\nd\n", ("b\n", "B1\nB2\n"), ("d", "D"))
        self.assertEqual((found.lines[0].first_line, found.lines[0].last_line, found.lines[1].first_line),
                         (2, 3, 5), "each edit's lines are where its text sits after every edit")
        self.assertEqual((found.sha256, found.note), (hashlib.sha256(written).hexdigest(), NOTE),
                         "the hash is the next call's expect_hash, and the built-in Edit needs a fresh Read")

    def test_an_interrupted_write_leaves_the_file_whole(self):
        folder = self.data / "work"
        folder.mkdir()
        (folder / "a.txt").write_bytes(b"one\r\ntwo\r\n")
        ctx = Context.fake(fs=LiveFs(), data_dir=self.data, platform=detect())
        with mock.patch("ioguard.lib.bytesio.os.replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_tool(edit, EditInput("a.txt", (EditPair("two", "2"),)), ctx, folder)
        self.assertEqual([path.name for path in folder.iterdir()], ["a.txt"], "no temporary file is left")
        self.assertEqual((folder / "a.txt").read_bytes(), b"one\r\ntwo\r\n",
                         "BYT-9: the file keeps its old bytes, never a truncated copy")


class ABatchIsRefusedWhole(EditTest):
    def test_a_missing_anchor_in_the_second_edit_writes_nothing_and_names_the_whole_fixed_call(self):
        ctx = self.context({CWD / "a.txt": b"one\n\ttwo\n"})
        given = EditInput("a.txt", (EditPair("one", "ONE"), EditPair("    two", "TWO")))
        result = self.refusal(edit, given, ctx)
        self.assertEqual((result.code, result.severity, result.fix.tool), (Code.ANCHOR_NOT_FOUND,
                                                                           Severity.REFUSED, EDIT),
                         "task 20's diagnosis, as a refusal whose fix calls io.edit")
        self.assertEqual(result.fix.input["edits"][1]["old_string"], "\ttwo",
                         "the fix is the whole call again, the second edit's old_string as the file holds it")
        self.assertTrue(result.message.startswith("io.edit wrote nothing. old_string of edit 2, looked for "
                                                  "after edit 1, matches line 2 of a.txt"),
                        "the message says nothing was written, and which edit missed where")

    def test_an_anchor_nothing_resembles_names_io_edit_as_the_retry(self):
        result = self.refusal(edit, EditInput("a.txt", (EditPair("LETTER=0", "LETTER=1"),)),
                              self.context({CWD / "a.txt": b"A=0\r\nB=0\r\n"}))
        self.assertEqual((result.code, result.fix.tool, "Call Edit" in result.render()),
                         (Code.ANCHOR_NOT_FOUND, EDIT, False),
                         "with no close lines to show, the fix still calls io.edit, never the built-in Edit")

    def test_a_repeated_anchor_is_ambiguous_with_no_replace_all(self):
        ctx = self.context({CWD / "a.txt": b"x\nx\n"})
        result = self.refusal(edit, EditInput("a.txt", (EditPair("x", "y"),)), ctx)
        self.assertEqual((result.code, "replace_all" in result.render()), (Code.ANCHOR_AMBIGUOUS, False),
                         "io.edit has no replace_all, so the fix does not offer one")

    def test_a_file_changed_since_its_hash_was_read_is_refused(self):
        data = b"one\n"
        self.assertEqual(self.edited(data, ("one", "1"), expect_hash=hashlib.sha256(data).hexdigest())[0],
                         b"1\n", "the hash the file has lets the edit through")
        result = self.refusal(edit, EditInput("a.txt", (EditPair("one", "1"),), "0" * 64),
                              self.context({CWD / "a.txt": data}))
        self.assertEqual((result.code, result.fix.tool), (Code.STALE_VIEW, callable_name("io.read")),
                         "another hash refuses, and the fix reads the file again")

    def test_what_io_edit_cannot_change_is_refused_by_code(self):
        arrow = EditInput("a.txt", (EditPair("za", chr(0x2192)),))
        for files, given, options, code in (
                ({}, None, {}, Code.PATH_NOT_FOUND),
                ({CWD / "a.txt": fixture("nul-byte.txt")}, None, {}, Code.ENCODING_INVALID),
                ({CWD / "a.txt": fixture("cp1250.txt")}, arrow, {}, Code.ENCODING_INVALID),
                ({CWD / "a.txt": b"x" * 20}, None, {"max_bytes": 10}, Code.READ_TOO_LARGE)):
            with self.subTest(code=code, given=given):
                given = given or EditInput("a.txt", (EditPair("x", "y"),))
                self.assertEqual(self.refusal(edit, given, self.context(files, **options)).code, code,
                                 "the model reads why, and nothing is written")

    def test_io_edit_refuses_a_read_only_file_before_writing(self):
        ctx = Context.fake(platform=WINDOWS, data_dir=self.data,
                           fs=FakeFs({CWD / "a.txt": b"x\n"}, readonly=frozenset({CWD / "a.txt"})))
        self.assertEqual(self.refusal(edit, EditInput("a.txt", (EditPair("x", "y"),)), ctx).code,
                         Code.READ_ONLY, "a read-only file is refused before the write fails")


class ASpliceReplacesBetweenMarkers(EditTest):
    def spliced(self, data: bytes, given: SpliceInput) -> bytes:
        ctx = self.context({CWD / "a.md": data})
        self.run_tool(splice, given, ctx)
        return ctx.fs.files[CWD / "a.md"]

    def test_the_text_between_the_markers_is_replaced_and_the_markers_stay(self):
        data = b"# A\r\nold\r\nold\r\n# B\r\nkeep\r\n"
        self.assertEqual(self.spliced(data, SpliceInput("a.md", "# A\n", "# B", "new\n")),
                         b"# A\r\nnew\r\n# B\r\nkeep\r\n", "the block changes in the file's CRLF")
        self.assertEqual(self.spliced(data, SpliceInput("a.md", "# A\n", "# B\n", "new\n", include_end=True)),
                         b"# A\r\nnew\r\nkeep\r\n", "include_end replaces the end marker too")

    def test_markers_that_do_not_mark_one_block_are_refused(self):
        def refused(start: str, end: str):
            return self.refusal(splice, SpliceInput("a.md", start, end, "y"),
                                self.context({CWD / "a.md": b"# A\nx\n# B\n# A\n"}))
        start = refused("# A", "# B")
        self.assertEqual((start.code, start.fix.tool, start.fix.input["start"]),
                         (Code.ANCHOR_AMBIGUOUS, callable_name("io.splice"), "# A\nx"),
                         "a start marker found twice gets the shortest one that names the first place")
        self.assertEqual(refused("x", "# A\n# A").code, Code.ANCHOR_NOT_FOUND,
                         "an end marker that is not after the start")
        before = refused("# B", "x")
        self.assertIn("only before the start marker, on line 2", before.message,
                      "an end marker found only before the start says where it is")


class AnAppendAddsLinesAtTheEnd(EditTest):
    def appended(self, data: bytes, given: AppendInput, files: dict | None = None) -> bytes:
        ctx = self.context({CWD / "a.md": data, **(files or {})})
        self.run_tool(append, given, ctx)
        return ctx.fs.files[CWD / "a.md"]

    def test_the_file_keeps_its_endings_and_its_last_line_break(self):
        for data, expected in ((b"a\r\n", b"a\r\nb\r\nc\r\n"), (b"a", b"a\nb\nc"), (b"", b"b\nc\n")):
            with self.subTest(data=data):
                self.assertEqual(self.appended(data, AppendInput("a.md", "b\nc\n")), expected,
                                 "a file with no last line break keeps having none")

    def test_the_editorconfig_column_wraps_when_no_column_is_given(self):
        files = {CWD / ".editorconfig": b"root = true\n[*.md]\nmax_line_length = 20\n"}
        self.assertEqual(self.appended(b"", AppendInput("a.md", "1. one two three four five six"), files),
                         b"1. one two three\n   four five six\n", "a numbered item hangs under its words")

    def test_empty_text_writes_nothing(self):
        ctx = self.context({CWD / "a.md": b"a\n"})
        self.assertFalse(self.run_tool(append, AppendInput("a.md", "\n"), ctx).changed,
                         "an empty append leaves the file as it was")


class CallsOnOneFileTakeTurns(EditTest):
    def counters(self) -> Path:
        folder = self.data / "work"
        folder.mkdir()
        (folder / "a.txt").write_bytes(b"A=0\nB=0\n")
        return folder / "a.txt"

    def test_two_threads_editing_one_file_both_land(self):
        target = self.counters()
        ctx = Context.fake(fs=LiveFs(), data_dir=self.data, platform=detect())
        failures = []

        def count(key: str) -> None:
            try:
                for step in range(40):
                    self.run_tool(edit, EditInput(str(target), (EditPair(f"{key}={step}\n",
                                                                         f"{key}={step + 1}\n"),)), ctx,
                                  target.parent)
            except ToolFailure as failure:
                failures.append(failure.result.render())
        threads = [threading.Thread(target=count, args=(key,)) for key in "AB"]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        self.assertEqual((failures, target.read_bytes()), ([], b"A=40\nB=40\n"),
                         "the lock table serialises the threads, so no edit reads a stale file")

    def test_two_processes_editing_one_file_both_land(self):
        target = self.counters()
        children = [subprocess.Popen([sys.executable, "-c", CHILD, str(PLUGIN_SCRIPTS), str(target),
                                      str(self.data), key, "40"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE) for key in "AB"]
        for child in children:
            self.assertEqual(child.stdout.readline().strip(), b"ready", "each child waits for the start")
        for child in children:
            child.stdin.write(b"go\n")
            child.stdin.flush()
        errors = [child.communicate(timeout=120)[1].decode("utf-8", "replace") for child in children]
        self.assertEqual(([child.returncode for child in children], target.read_bytes()),
                         ([0, 0], b"A=40\nB=40\n"), f"file_lock serialises the processes: {errors}")


if __name__ == "__main__":
    unittest.main()
