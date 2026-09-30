"""io.format runs the user's format command over the lines each file changed since its last commit, and
lands the result in the file's own endings, BOM and encoding, or writes nothing to any file."""
import os
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType

from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.git import Git
from ioguard.lib.platform import detect
from ioguard.lib.ports import LiveFs
from ioguard.lib.results import Code, Severity
from ioguard.mcp.in_place import Place
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_format import FormatInput, format_files
from ioguard.mcp.toolspec import InvalidArguments, ToolCall, ToolFailure
from tests.support import shells
from tests.support.project import TemporaryProject

FORMATTER = """
import sys
ranges = [tuple(int(n) for n in arg[8:].split(":")) for arg in sys.argv[1:] if arg.startswith("--lines=")]
if "--fail" in sys.argv:
    sys.stderr.write("style file, line 2: unknown key\\n")
    sys.exit(1)
if "--silent" in sys.argv:
    sys.exit(0)
given = sys.stdin.buffer.read().decode("utf-8")
if "\\r" in given:
    sys.exit(3)
lines = given.split("\\n")
body = [line.upper() if any(first <= number <= last for first, last in ranges) else line
        for number, line in enumerate(lines, 1)]
if "--closer" in sys.argv:
    body.insert(-1, "// END")
sys.stdout.buffer.write("\\r\\n".join(body).encode("utf-8"))
"""
BOM = chr(0xFEFF)
CPP = (BOM + "int a;\r\nint b;\r\nint c;\r\nint d;\r\n").encode("utf-8")


class FormatTest(unittest.TestCase):
    """A git project, and a formatter that upper-cases the lines it is given, reads stdin as LF only, and
    writes CRLF whatever the file holds, as clang-format with a fixed LineEnding does."""

    def setUp(self):
        self.tools = Path(tempfile.mkdtemp(prefix="ioguard-format-"))
        self.addCleanup(shutil.rmtree, self.tools, True)
        (self.tools / "upper.py").write_text(FORMATTER, encoding="utf-8")

    def command(self, *extra: str) -> list[str]:
        return [sys.executable, str(self.tools / "upper.py"), "--lines={first}:{last}", *extra]

    def context(self, **commands) -> Context:
        values = {**defaults().values, "format": {".cpp": self.command(), **commands}}
        return Context.fake(config=Config(MappingProxyType(values)), fs=LiveFs(), git=Git(),
                            platform=detect(), data_dir=self.tools / "data", env=dict(os.environ))

    def call(self, root: Path, given: FormatInput, ctx: Context):
        return format_files(given, ToolCall(lambda: ctx, CancelToken(), root, None))

    def refusal(self, root: Path, given: FormatInput, ctx: Context):
        with self.assertRaises(ToolFailure) as failure:
            self.call(root, given, ctx)
        return failure.exception.result


class OnlyTheChangedLinesAreFormatted(FormatTest):
    def test_the_lines_changed_since_the_last_commit_land_in_the_files_own_bytes(self):
        with TemporaryProject({"a.cpp": CPP}, git=True) as root:
            (root / "a.cpp").write_bytes(CPP.replace(b"int b;", b"int bb;").replace(b"int d;", b"int dd;"))
            found = self.call(root, FormatInput(["a.cpp"]), self.context()).files[0]
            self.assertEqual((root / "a.cpp").read_bytes(),
                             (BOM + "int a;\r\nINT BB;\r\nint c;\r\nINT DD;\r\n").encode("utf-8"),
                             "BYT-12 and BYT-3: lines 2 and 4 are formatted, the rest are not, and the file "
                             "keeps its BOM and CRLF")
            self.assertEqual((found.asked, found.lines, found.changed, found.formatter),
                             ([Place(2, 2), Place(4, 4)], [Place(2, 2), Place(4, 4)], True, "python"),
                             "the result names the lines asked and the lines changed")

    def test_a_file_git_has_no_commit_of_is_formatted_whole(self):
        with TemporaryProject({"a.cpp": b"x\ny\n"}) as root:
            found = self.call(root, FormatInput([str(root / "a.cpp")]), self.context()).files[0]
            self.assertEqual(((root / "a.cpp").read_bytes(), found.reason),
                             (b"X\nY\n", "the whole file, which git has no commit of"),
                             "an untracked file counts as changed whole, and keeps its LF")

    @unittest.skipUnless(sys.platform == "win32" and shells.git_folder(), "Git Bash runs on Windows only")
    def test_a_formatter_the_bash_tool_finds_in_git_s_folders_runs(self):
        ctx = self.context(**{".cpp": ["tr", "a-z", "A-Z"]})
        probe = replace(ctx.probe, bash=shells.git_bash())
        ctx = replace(ctx, env=shells.without_git_tools(ctx.env), probe=probe)
        with TemporaryProject({"a.cpp": b"x\ny\n"}) as root:
            self.call(root, FormatInput([str(root / "a.cpp")]), ctx)
            self.assertEqual((root / "a.cpp").read_bytes(), b"X\nY\n",
                             "tr, which the Bash tool finds in Git's usr/bin, runs as the format command")

    def test_the_lines_a_call_names_are_formatted_instead(self):
        with TemporaryProject({"a.cpp": b"a\nb\nc\n"}, git=True) as root:
            self.call(root, FormatInput(["a.cpp"], {"a.cpp": [Place(3, 9)]}), self.context())
            self.assertEqual((root / "a.cpp").read_bytes(), b"a\nb\nC\n",
                             "lines names the range, cut at the file's last line")

    def test_a_change_the_formatter_makes_away_from_the_lines_stays_as_it_was(self):
        with TemporaryProject({"a.cpp": b"a\nb\nc\nd\n"}, git=True) as root:
            (root / "a.cpp").write_bytes(b"A1\nb\nc\nd\n")
            ctx = self.context(**{".cpp": self.command("--closer")})
            found = self.call(root, FormatInput(["a.cpp"]), ctx).files[0]
            self.assertEqual(((root / "a.cpp").read_bytes(), found.left), (b"A1\nb\nc\nd\n", [Place(4, 4)]),
                             "BYT-12: the line the formatter added far from line 1 is left out, and the "
                             "result names where")


class AFileWithNothingToFormatStaysAsItIs(FormatTest):
    def test_no_command_and_no_changed_line_leave_the_file_alone(self):
        with TemporaryProject({"a.cpp": b"a\n", "b.md": b"# b\n"}, git=True) as root:
            found = self.call(root, FormatInput(["a.cpp", "b.md"]), self.context()).files
            self.assertEqual([(each.changed, each.formatter, each.reason) for each in found],
                             [(False, "", "no line changed since the last commit"),
                              (False, "", "the format key in config.json names no command for .md")],
                             "each file says why nothing ran")
            self.assertEqual(((root / "a.cpp").read_bytes(), (root / "b.md").read_bytes()),
                             (b"a\n", b"# b\n"), "neither file is written")


    def test_a_file_outside_the_project_takes_no_command_from_the_projects_file(self):
        with (TemporaryProject(git=True) as project,
              TemporaryProject({"a.cpp": b"a\nb\n"}, git=True) as other):
            mine = Config(MappingProxyType({**defaults().values, "format": {}}))
            ctx = replace(self.context(), project=project, outside=mine,
                          held={"format": {".cpp": ["x", "{first}-{last}"]}})
            found = self.call(project, FormatInput([str(other / "a.cpp")], {str(other / "a.cpp"):
                                                                          [Place(1, 2)]}), ctx)
            self.assertEqual(((other / "a.cpp").read_bytes(), found.files[0].reason, found.waiting),
                             (b"a\nb\n", "the format key in config.json names no command for .cpp", ""),
                             "one project's format command and waiting commands never reach another's files")


class AFailureWritesNothing(FormatTest):
    def test_a_formatter_that_fails_on_one_file_leaves_every_file_as_it_was(self):
        with TemporaryProject({"a.cpp": b"a\n", "b.h": b"b\n"}) as root:
            ctx = self.context(**{".h": self.command("--fail")})
            result = self.refusal(root, FormatInput(["a.cpp", "b.h"]), ctx)
            self.assertEqual((result.code, result.severity, (root / "a.cpp").read_bytes()),
                             (Code.FORMAT_FAILED, Severity.REFUSED, b"a\n"),
                             "a.cpp formatted in memory is not written when b.h fails")
            self.assertIn("style file, line 2: unknown key", result.message,
                          "the formatter's own words reach the model")

    def test_a_missing_program_or_one_that_prints_nothing_is_refused(self):
        missing = [str(Path(tempfile.gettempdir()) / "no-such-formatter.exe"), "--l={first}:{last}"]
        for command, words in ((missing, "could not start"), (self.command("--silent"), "printed nothing")):
            with self.subTest(words=words), TemporaryProject({"a.cpp": b"a\n"}) as root:
                result = self.refusal(root, FormatInput(["a.cpp"]), self.context(**{".cpp": command}))
                self.assertEqual((result.code, words in result.message, (root / "a.cpp").read_bytes()),
                                 (Code.FORMAT_FAILED, True, b"a\n"),
                                 "a formatter that cannot run, or writes over the file instead of printing, "
                                 "never empties it")

    def test_lines_for_a_file_paths_does_not_name_or_running_backwards_are_refused(self):
        with TemporaryProject({"a.cpp": b"a\n"}) as root:
            for given in (FormatInput(["a.cpp"], {"b.cpp": [Place(1, 1)]}), FormatInput([]),
                          FormatInput(["a.cpp"], {"a.cpp": [Place(3, 2)]})):
                with self.subTest(given=given):
                    with self.assertRaises(InvalidArguments, msg="lines are keyed by a path from paths"):
                        self.call(root, given, self.context())


class ADryRunShowsWhatWouldChange(FormatTest):
    def test_a_dry_run_returns_the_diff_and_writes_nothing(self):
        with TemporaryProject({"a.cpp": CPP}, git=True) as root:
            changed = CPP.replace(b"int b;", b"int bb;")
            (root / "a.cpp").write_bytes(changed)
            output = self.call(root, FormatInput(["a.cpp"], dry_run=True), self.context())
            found = output.files[0]
            self.assertEqual(((root / "a.cpp").read_bytes(), found.changed, output.written_bytes()),
                             (changed, True, 0), "the file keeps its bytes, and the result says it would")
            self.assertIn("-int bb;\n+INT BB;", found.diff, "the diff shows the line as it is and would be")
            self.assertIn("would change line 2", output.render(), "the words say nothing was written")

    def test_each_file_takes_its_own_lines_in_one_call(self):
        with TemporaryProject({"a.cpp": b"a\nb\n", "b.cpp": b"c\nd\n"}, git=True) as root:
            lines = {"a.cpp": [Place(1, 1)], str(root / "b.cpp"): [Place(2, 2)]}
            self.call(root, FormatInput(["a.cpp", "b.cpp"], lines), self.context())
            self.assertEqual(((root / "a.cpp").read_bytes(), (root / "b.cpp").read_bytes()),
                             (b"A\nb\n", b"c\nD\n"), "lines keyed by either spelling of a path narrow it")


@unittest.skipUnless(shutil.which("clang-format"), "clang-format is not on PATH")
class TheDefaultRunsClangFormat(unittest.TestCase):
    def test_clang_format_formats_the_changed_function_and_keeps_crlf(self):
        style = b"BasedOnStyle: LLVM\nLineEnding: LF\n"
        source = b"int  a=1;\r\nint  b=2;\r\n"
        with TemporaryProject({".clang-format": style, "a.cpp": source}, git=True) as root:
            (root / "a.cpp").write_bytes(source + b"void f(){if(x){y();}}\r\n")
            ctx = Context.fake(fs=LiveFs(), git=Git(), platform=detect(), env=dict(os.environ),
                               data_dir=root / ".data")
            found = format_files(FormatInput(["a.cpp"]), ToolCall(lambda: ctx, CancelToken(), root, None))
            self.assertEqual((root / "a.cpp").read_bytes(),
                             source + b"void f() {\r\n  if (x) {\r\n    y();\r\n  }\r\n}\r\n",
                             "clang-format formats the new line, leaves lines 1 and 2 as they were although "
                             "the style asks for LF, and every line keeps CRLF")
            self.assertEqual(found.files[0].formatter, "clang-format", "the default command is clang-format")


if __name__ == "__main__":
    unittest.main()
