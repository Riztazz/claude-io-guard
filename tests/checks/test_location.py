"""write.location refuses a device name and a read-only file, names the repository a linked path writes into,
and points out a file dirty at session start. write.locks names the process that holds a locked file."""
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import defaults
from ioguard.lib.context import Context, SessionState
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeFs, FakeGit
from ioguard.lib.locks import Process
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code
from tests.support import events

CWD = Path("C:/game")
KIT = Path("C:/kit")
WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)
REGISTRY = default_registry()
EPERM = "EPERM: operation not permitted, rename 'C:\\game\\a.cpp.tmp.1.0f' -> 'C:\\game\\a.cpp'"


def context(fs: FakeFs | None = None, git: FakeGit | None = None, platform: Platform = WINDOWS,
            dirty: tuple[Path, ...] | None = None) -> Context:
    return Context.fake(config=defaults(REGISTRY.keys()), platform=platform,
                        session=SessionState(dirty=dirty), fs=fs or FakeFs({}), git=git or FakeGit(root=CWD))


def write(path: Path, ctx: Context):
    raw = events.write(path, "x\n", CWD)
    return Pipeline(REGISTRY).run(Event.from_hook_json(raw, Surface.MCP_HOOK, ctx.platform), ctx)


def found(outcome, check_id: str = "write.location"):
    return [result for decision in outcome.decisions if decision.check_id == check_id
            for result in decision.results]


class DeviceNamesAndReadOnlyFilesAreRefused(unittest.TestCase):
    def test_a_device_name_is_refused_on_windows_only(self):
        windows, macos = write(CWD / "nul.txt", context()), write(CWD / "nul.txt", context(platform=MACOS))
        self.assertEqual((windows.verdict, found(windows)[0].code, macos.verdict),
                         (Verdict.DENY, Code.RESERVED_NAME, Verdict.OBSERVE),
                         "nul.txt is the NUL device on Windows and an ordinary name on macOS")

    def test_a_read_only_file_is_refused(self):
        path = CWD / "a.cpp"
        outcome = write(path, context(FakeFs({path: b"x\n"}, readonly=frozenset({path}))))
        self.assertEqual((outcome.verdict, found(outcome)[0].code, found(outcome)[0].fix),
                         (Verdict.DENY, Code.READ_ONLY, None),
                         "a read-only file is refused, and the general step is to ask the user")

    def test_a_lockable_file_gets_the_git_lfs_lock_step(self):
        path = CWD / "Content" / "Hero.uasset"
        git = FakeGit(root=CWD, attributes={path: {"lockable": "set"}})
        outcome = write(path, context(FakeFs({path: b"x"}, readonly=frozenset({path})), git))
        self.assertEqual(found(outcome)[0].fix.input, {"command": "git lfs lock Content/Hero.uasset"},
                         "an LFS-lockable file is unlocked with git lfs lock, from the repository root")


class LinksIntoAnotherRepositoryAreNamed(unittest.TestCase):
    def linked(self, tracked: frozenset[Path] = frozenset()):
        fs = FakeFs({}, links={CWD / ".claude" / "skills": KIT / "skills"})
        return context(fs, FakeGit(root=CWD, other_roots=(KIT,), tracked=tracked))

    def test_a_write_through_a_link_names_the_owning_repository(self):
        outcome = write(CWD / ".claude" / "skills" / "a.md", self.linked())
        result = found(outcome)[0]
        self.assertEqual((outcome.verdict, result.code, result.evidence["owner"]),
                         (Verdict.ALLOW, Code.LINKED_PATH, "C:/kit"),
                         "the write goes ahead, and the model learns which repository it changes")

    def test_a_tracked_link_is_warned_about_once_per_session(self):
        path = CWD / ".claude" / "skills" / "a.md"
        ctx = self.linked(tracked=frozenset({path}))
        first, second = found(write(path, ctx)), found(write(path, ctx))
        self.assertEqual((len(first), len(second)), (2, 1),
                         "the note comes each time, and the warning about discards and stashes once")
        self.assertIn("a discard, stash or branch switch there writes into C:/kit", first[1].message,
                      "the warning names what writes through the link")

    def test_a_link_inside_the_same_repository_says_nothing(self):
        fs = FakeFs({}, links={CWD / "alias": CWD / "real"})
        self.assertEqual(found(write(CWD / "alias" / "a.txt", context(fs))), [],
                         "a link that stays in the project changes no other repository")


class ADirtyFileIsPointedOutOnce(unittest.TestCase):
    def test_the_first_write_to_a_file_dirty_at_start_gets_one_line(self):
        path = CWD / "a.cpp"
        ctx = context(FakeFs({path: b"x\n"}), dirty=(path,))
        first, second = write(path, ctx), write(path, ctx)
        self.assertIn("already had uncommitted changes when this session started", first.context[0],
                      "the model learns the changes it finds are not its own")
        self.assertFalse(any("uncommitted" in line for line in second.context), "the line comes once")


class ALockedFileNamesItsHolder(unittest.TestCase):
    def failed(self, error: str, fs: FakeFs):
        raw = events.post_tool_use_failure("Edit", {"file_path": str(CWD / "a.cpp"), "old_string": "a",
                                                    "new_string": "b"}, error, CWD)
        ctx = context(fs)
        return Pipeline(REGISTRY).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), ctx)

    def test_the_holding_process_is_named(self):
        fs = FakeFs({}, holders={CWD / "a.cpp": (Process(4242, "UnrealEditor.exe"),)})
        result = found(self.failed(EPERM, fs), "write.locks")[0]
        message = "UnrealEditor.exe (process 4242) holds a.cpp open, so the Edit tool could not replace it."
        self.assertEqual((result.code, result.message), (Code.FILE_LOCKED, message),
                         "the model learns which program to close or wait for")

    def test_a_holder_that_let_go_and_another_failure_are_told_apart(self):
        let_go = found(self.failed(EPERM, FakeFs({})), "write.locks")[0].message
        other = found(self.failed("String to replace not found in file.", FakeFs({})), "write.locks")
        self.assertEqual(("let go by the time io-guard looked" in let_go, other), (True, []),
                         "an EPERM with no holder left says so, and a failure that is no lock says nothing")


if __name__ == "__main__":
    unittest.main()
