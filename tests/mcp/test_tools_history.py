"""io.snapshot keeps files by tag, and io.restore writes back only the files that changed, and only after the
PreToolUse hook on its call put the restore to the user."""
import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.checks.restore_ask import RestoreAsk
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context, LiveFs
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeFs
from ioguard.lib.platform import Platform, detect
from ioguard.lib.results import Code, callable_name
from ioguard.mcp.progress import CancelToken
from ioguard.mcp.tools_history import (CompareInput, RestoreInput, SnapshotInput, compare, restore,
                                       snapshot)
from ioguard.mcp.toolspec import InvalidArguments, ToolCall, ToolFailure
from tests.support import events

CWD = Path("C:/project")
WINDOWS = Platform("win32", True)


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="ioguard-history-"))
        self.addCleanup(shutil.rmtree, self.home, True)

    def context(self, files: dict, **config) -> Context:
        values = {**defaults().values, **config}
        return Context.fake(config=Config(MappingProxyType(values)), platform=WINDOWS, fs=FakeFs(files),
                            data_dir=self.home)

    @staticmethod
    def call(handler, given, ctx: Context, cwd: Path = CWD):
        return handler(given, ToolCall(lambda: ctx, CancelToken(), cwd, None))

    def refusal(self, handler, given, ctx: Context):
        with self.assertRaises(ToolFailure) as failure:
            self.call(handler, given, ctx)
        return failure.exception.result

    @staticmethod
    def asked(ctx: Context, tool_input: dict, cwd: Path = CWD):
        """The PreToolUse hook on an io.restore call, as the server runs it."""
        registry = Registry()
        registry.register(RestoreAsk)
        raw = events.pre_tool_use(callable_name("io.restore"), tool_input, cwd)
        return Pipeline(registry).run(Event.from_hook_json(raw, Surface.MCP_HOOK, ctx.platform), ctx)


class SnapshotKeepsTheFilesNamed(HistoryTest):
    FILES = {CWD / "src" / "a.cpp": b"int a;\r\n", CWD / "src" / "deep" / "b.cpp": b"int b;\n",
             CWD / "src" / "c.h": b"#pragma once\n", CWD / "notes.md": b"# notes\n"}

    def test_a_glob_a_folder_and_a_file_each_count_once(self):
        ctx = self.context(self.FILES)
        kept = self.call(snapshot, SnapshotInput(["src/**/*.cpp", "src", "notes.md"], "pass"), ctx)
        self.assertEqual((kept.files, kept.tag, ctx.session.tag), (4, "pass", "pass"),
                         "a glob, a folder and a file together name four files, each kept once")
        self.assertEqual(kept.bytes, sum(len(data) for data in self.FILES.values()), "every byte is kept")

    def test_a_path_that_names_no_file_is_refused(self):
        result = self.refusal(snapshot, SnapshotInput(["src/*.py"], "pass"), self.context(self.FILES))
        self.assertEqual(result.code, Code.PATH_NOT_FOUND, "a glob that meets no file keeps nothing")

    def test_more_files_or_bytes_than_a_snapshot_keeps_are_refused(self):
        for config in ({"io.snapshot.max_files": 3}, {"io.snapshot.max_bytes": 20}):
            with self.subTest(config=config):
                ctx = self.context(self.FILES, **config)
                result = self.refusal(snapshot, SnapshotInput(["src", "notes.md"], "pass"), ctx)
                self.assertEqual(result.code, Code.SNAPSHOT_TOO_LARGE, "past a limit, nothing is kept")

    def test_an_empty_tag_is_not_one_call(self):
        with self.assertRaises(InvalidArguments):
            self.call(snapshot, SnapshotInput(["notes.md"], " "), self.context(self.FILES))


class RestoreWritesBackOnlyWhatChangedAndOnlyWhenAsked(HistoryTest):
    def kept_then_edited(self) -> Context:
        ctx = self.context({CWD / "a.txt": b"one\r\n", CWD / "b.txt": b"two\n"})
        self.call(snapshot, SnapshotInput(["a.txt", "b.txt"], "pass"), ctx)
        ctx.fs.files[CWD / "a.txt"] = b"one\r\nchanged\r\n"
        return ctx

    def test_the_hook_asks_and_the_restore_it_asked_about_writes_back(self):
        ctx = self.kept_then_edited()
        outcome = self.asked(ctx, {"tag": "pass"})
        result = outcome.decisions[0].results[0]
        self.assertEqual((outcome.verdict, result.code), (Verdict.ASK, Code.RESTORE_ASKED),
                         "a restore over an edited file goes to the user's permission prompt")
        self.assertIn("a.txt", result.message, "the question names the file whose edits it would lose")
        done = self.call(restore, RestoreInput("pass"), ctx)
        self.assertEqual((ctx.fs.files[CWD / "a.txt"], done.restored, done.unchanged),
                         (b"one\r\n", ["C:/project/a.txt"], ["C:/project/b.txt"]),
                         "only the changed file is written, back to its kept bytes")

    def test_a_restore_the_hook_never_asked_about_writes_nothing(self):
        ctx = self.kept_then_edited()
        result = self.refusal(restore, RestoreInput("pass"), ctx)
        self.assertEqual((result.code, ctx.fs.files[CWD / "a.txt"]),
                         (Code.RESTORE_ASKED, b"one\r\nchanged\r\n"),
                         "a hook that failed open lets no restore through")

    def test_an_answer_is_spent_on_one_restore(self):
        ctx = self.kept_then_edited()
        self.asked(ctx, {"tag": "pass"})
        self.call(restore, RestoreInput("pass"), ctx)
        ctx.fs.files[CWD / "a.txt"] = b"edited again\r\n"
        self.assertEqual(self.refusal(restore, RestoreInput("pass"), ctx).code, Code.RESTORE_ASKED,
                         "the user's yes covers the restore it was asked about, once")

    def test_nothing_changed_needs_no_question(self):
        ctx = self.context({CWD / "a.txt": b"one\n"})
        self.call(snapshot, SnapshotInput(["a.txt"], "pass"), ctx)
        self.assertEqual(self.asked(ctx, {"tag": "pass"}).verdict, Verdict.OBSERVE,
                         "a restore that writes nothing asks nothing")
        self.assertEqual(self.call(restore, RestoreInput("pass"), ctx).restored, [], "and it writes nothing")

    def test_a_tag_no_snapshot_holds_is_expired(self):
        result = self.refusal(restore, RestoreInput("never"), self.context({}))
        self.assertEqual(result.code, Code.HANDLE_EXPIRED, "the fix is io.snapshot before the next task")

    def test_a_path_the_snapshot_never_kept_is_named(self):
        ctx = self.kept_then_edited()
        result = self.refusal(restore, RestoreInput("pass", ["c.txt"]), ctx)
        self.assertEqual(result.code, Code.PATH_NOT_FOUND, "a restore of a file never kept writes nothing")


class CompareShowsWhetherAPassChangedCode(HistoryTest):
    def compared(self, mode: str = "code", paths: list | None = None):
        ctx = self.context({CWD / "a.cpp": b"int a; // old\n", CWD / "b.cpp": b"int b = 1;\n",
                            CWD / "c.txt": b"same\n", CWD / "d.h": b"#pragma once\n"})
        self.call(snapshot, SnapshotInput(["*"], "pass"), ctx)
        ctx.fs.files[CWD / "a.cpp"] = b"// header\nint a; // new\n"
        ctx.fs.files[CWD / "b.cpp"] = b"// header\nint b = 2;\n"
        del ctx.fs.files[CWD / "d.h"]
        return self.call(compare, CompareInput("pass", mode, paths or []), ctx)

    def test_a_comment_pass_is_same_and_a_code_change_is_named_with_its_lines(self):
        found = self.compared()
        self.assertEqual(found.same, ["C:/project/a.cpp", "C:/project/c.txt"],
                         "a.cpp changed only comments, and c.txt did not change at all")
        changed = {each.path: each for each in found.differ}
        b = changed["C:/project/b.cpp"]
        self.assertEqual((b.before_line, b.after_line, b.before, b.after), (1, 2, "int b = 1;", "int b = 2;"),
                         "the result quotes the line whose code changed, on each side")
        self.assertEqual(changed["C:/project/d.h"].after_line, 0, "a file that is gone differs, at no line")
        self.assertIn("2 of 4 files hold the same code", found.render(), "the text leads with the count")

    def test_exact_mode_counts_the_comment_pass_as_a_change(self):
        found = self.compared("exact", ["a.cpp", "c.txt"])
        self.assertEqual((found.same, [each.path for each in found.differ]),
                         (["C:/project/c.txt"], ["C:/project/a.cpp"]), "exact compares every line")

    def test_an_unknown_mode_is_not_one_call(self):
        with self.assertRaises(InvalidArguments):
            self.compared("tokens")


class ABatchOfTenFilesRestoresExactly(HistoryTest):
    def test_every_file_hash_matches_its_before_copy(self):
        project = Path(tempfile.mkdtemp(prefix="ioguard-project-"))
        self.addCleanup(shutil.rmtree, project, True)
        bodies = [b"lf\n", b"crlf\r\n", b"\xef\xbb\xbfbom\r\n", b"no end", b"", b"\x00\x01binary",
                  "caf\u00e9\n".encode("utf-8"), "caf\u00e9\r\n".encode("cp1250"), b"\tindent\n",
                  b"x" * 70_000]
        for number, body in enumerate(bodies):
            (project / f"f{number}.txt").write_bytes(body)
        before = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in project.iterdir()}
        ctx = Context.fake(platform=detect(), fs=LiveFs(), data_dir=self.home)
        self.call(snapshot, SnapshotInput(["*.txt"], "batch"), ctx, project)
        for number, path in enumerate(sorted(project.iterdir())):
            if number == 3:
                path.unlink()
            else:
                path.write_bytes(path.read_bytes() + b"\nedit")
        self.assertEqual(self.asked(ctx, {"tag": "batch"}, project).verdict, Verdict.ASK,
                         "the user is asked")
        done = self.call(restore, RestoreInput("batch"), ctx, project)
        after = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in project.iterdir()}
        self.assertEqual((after, len(done.restored)), (before, 10),
                         "all ten files, the deleted one too, hash as they did before the task")


if __name__ == "__main__":
    unittest.main()
