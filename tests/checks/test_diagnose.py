"""diagnose.failure answers a failed Read, Grep or Glob, and diagnose.refused answers, at the next hook, an
Edit or Write that Claude Code refused before any hook ran."""
import json
import unittest
from pathlib import Path

from ioguard.checks.diagnose import Diagnosis, Failed, Wording
from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import defaults
from ioguard.lib.context import Context
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeFs, FakeGit
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code
from tests.support import events

CWD = Path("C:/game")
TRANSCRIPT = CWD / ".transcript.jsonl"
WINDOWS = Platform("win32", True)
REGISTRY = default_registry()
SOURCE = b"void f()\r\n{\r\n\tint a = 1;\r\n\tint b = 2;\r\n\tint a = 1;\r\n}\r\n"
MISSING = "File does not exist. Note: your current working directory is C:\\game."
REJECTED = "Search failed - ripgrep rejected the pattern, glob, or file type without searching:\nrg: regex " \
           "parse error:\n"


def context(files: dict | None = None, git: FakeGit | None = None) -> Context:
    return Context.fake(config=defaults(REGISTRY.keys()), platform=WINDOWS, fs=FakeFs(files or {}),
                        git=git or FakeGit(root=None))


def failed(tool: str, given: dict, error: str, ctx: Context):
    raw = events.post_tool_use_failure(tool, given, error, CWD)
    return Pipeline(REGISTRY).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), ctx)


def results(outcome, check_id: str):
    return [result for decision in outcome.decisions if decision.check_id == check_id
            for result in decision.results]


def refusal(tool: str, given: dict, error: str) -> bytes:
    """A transcript tail whose last call Claude Code refused."""
    use = {"type": "assistant", "cwd": str(CWD), "message": {"content": [
        {"type": "tool_use", "id": "toolu_refused", "name": tool, "input": given}]}}
    answer = {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "toolu_refused", "is_error": True,
         "content": f"<tool_use_error>{error}</tool_use_error>"}]}}
    return json.dumps(use).encode() + b"\n" + json.dumps(answer).encode() + b"\n"


def next_hook(ctx: Context):
    """The session's next hook after the refusal: a Read of the file, as a model rereads after a miss."""
    raw = events.read(CWD / "a.cpp", CWD)
    return Pipeline(REGISTRY).run(Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS), ctx)


def refused_edit(old: str, error: str, new: str = "int c = 3;"):
    given = {"file_path": str(CWD / "a.cpp"), "old_string": old, "new_string": new, "replace_all": False}
    ctx = context({CWD / "a.cpp": SOURCE, TRANSCRIPT: refusal("Edit", given, error)})
    return results(next_hook(ctx), "diagnose.refused"), ctx


class ARefusedEditIsAnsweredAtTheNextHook(unittest.TestCase):
    def test_spaces_for_a_tab_get_the_corrected_old_string(self):
        found, _ = refused_edit("    int b = 2;",
                                "String to replace not found in file.\nString:     int b = 2;")
        self.assertEqual((found[0].code, found[0].fix.input["old_string"]),
                         (Code.ANCHOR_NOT_FOUND, "\tint b = 2;"),
                         "the file's own text, with its tab, is the old_string to send")
        self.assertIn("uses CRLF line endings", found[0].message, "the file's ending style is named")
        self.assertIn('"\\tint b = 2;"', found[0].fix.text, "the corrected old_string is quoted exactly")

    def test_a_near_miss_shows_the_closest_lines_with_markers(self):
        found, _ = refused_edit("int b = 22;", "String to replace not found in file.\nString: int b = 22;")
        self.assertIn("4| [TAB]int b = 2;", found[0].message, "the closest line is numbered, its tab marked")

    def test_a_repeated_anchor_lists_each_place_and_a_unique_one(self):
        found, _ = refused_edit("\tint a = 1;", "Found 2 matches of the string to replace, but replace_all "
                                                "is false.")
        self.assertEqual((found[0].code, found[0].evidence["lines"], found[0].fix.input["old_string"]),
                         (Code.ANCHOR_AMBIGUOUS, [3, 5], "\tint a = 1;\n\tint b = 2;"),
                         "each place, and the line below that makes the first one unique")

    def test_identical_strings_get_only_claude_codes_own_error(self):
        found, _ = refused_edit("\tint b = 2;", "No changes to make: old_string and new_string are exactly "
                                                "the same.", new="\tint b = 2;")
        self.assertEqual(found, [], "Claude Code's error already says there is nothing to change")

    def test_an_edit_refused_after_the_file_changed_shows_the_lines_as_they_are_now(self):
        found, _ = refused_edit("\tint b = 2;", "File has been modified since read, either by the user or by "
                                                "a linter. Read it again before attempting to write it.")
        self.assertEqual(found[0].code, Code.STALE_VIEW, "the file changed after the Read")
        self.assertIn("Line 4 read now", found[0].message, "the lines as they are now follow")

    def test_a_refusal_is_answered_once(self):
        _, ctx = refused_edit("    int b = 2;", "String to replace not found in file.")
        self.assertEqual(results(next_hook(ctx), "diagnose.refused"), [],
                         "the hook after that has nothing new to say")

    def test_an_edit_of_a_missing_file_names_the_files_of_that_name(self):
        given = {"file_path": str(CWD / "Source" / "a.cpp"), "old_string": "x", "new_string": "y"}
        ctx = context({TRANSCRIPT: refusal("Edit", given, "File does not exist."),
                       CWD / "Private" / "a.cpp": b"x"})
        found = results(next_hook(ctx), "diagnose.refused")
        self.assertEqual((found[0].code, found[0].evidence["nearby"]),
                         (Code.PATH_NOT_FOUND, ["C:/game/Private/a.cpp"]),
                         "a walk from the nearest folder that exists finds the file by its name")


class AnIoToolReusesTheDiagnosis(unittest.TestCase):
    def test_its_wording_names_its_own_argument_and_call_and_reads_text_it_has_not_written(self):
        wording = Wording("the start marker", "start", "io_splice", replace_all=False)
        failed = Failed("io.splice", {"path": "a.cpp", "start": "int a = 1;"}, "", CWD, wording)
        found = Diagnosis(failed, context(), {}, contents=SOURCE).anchor_ambiguous()[0]
        self.assertEqual((found.code, found.fix.tool, found.fix.input["start"]),
                         (Code.ANCHOR_AMBIGUOUS, "io_splice", "\tint a = 1;\n\tint b = 2;"),
                         "the fix corrects the tool's own argument, found in the contents it was handed")
        self.assertEqual((found.message.startswith("the start marker is in a.cpp 2 times"),
                          "replace_all" in found.fix.text), (True, False),
                         "the message names the marker, and a tool with no replace_all is offered none")


class AFailedCallIsAnsweredAfterIt(unittest.TestCase):
    def test_a_missing_read_names_the_tracked_files_of_that_name(self):
        git = FakeGit(root=CWD, tracked=frozenset({CWD / "Source" / "Hero.h", CWD / "Other.h"}))
        outcome = failed("Read", {"file_path": str(CWD / "Hero.h")}, MISSING, context(git=git))
        found = results(outcome, "diagnose.failure")
        message = "Hero.h does not exist. Paths with the same name: Source/Hero.h."
        self.assertEqual((found[0].code, found[0].message), (Code.PATH_NOT_FOUND, message),
                         "git's list of files gives the path that exists")

    def test_a_read_too_large_gets_parts_that_fit(self):
        big = b"".join(b"line %06d of a big file\n" % number for number in range(20_000))
        outcome = failed("Read", {"file_path": str(CWD / "big.log")},
                         "File content (480.5KB) exceeds maximum allowed size (256KB).",
                         context({CWD / "big.log": big}))
        found = results(outcome, "diagnose.failure")[0]
        self.assertEqual((found.code, found.fix.input["limit"]), (Code.READ_TOO_LARGE, 2_000),
                         "a part of 2,000 lines of 24 bytes fits under the part size")

    def test_a_rejected_pattern_gets_a_literal_one(self):
        found = results(failed("Grep", {"pattern": "f(x"}, REJECTED + "    (\nerror: unclosed group",
                               context()), "diagnose.failure")[0]
        self.assertEqual((found.code, found.fix.input["pattern"]), (Code.PATTERN_INVALID, "f\\(x"),
                         "the pattern with its regex characters escaped searches the text as written")
        self.assertIn("unclosed group", found.message, "ripgrep's reason is named")

    def test_look_around_is_named_as_the_engine_s_limit(self):
        error = REJECTED + "error: look-around, including look-ahead and look-behind, is not supported"
        found = results(failed("Grep", {"pattern": "(?<=a)b"}, error, context()), "diagnose.failure")[0]
        self.assertIn("without look-around", found.fix.text, "the fix names what ripgrep lacks")

    def test_a_missing_path_outside_the_session_folder_is_not_walked_for(self):
        ctx = context({Path("C:/other/Hero.h"): b"x"})
        outcome = failed("Read", {"file_path": "C:/elsewhere/Hero.h"}, MISSING, ctx)
        found = results(outcome, "diagnose.failure")[0]
        self.assertEqual((found.message, found.evidence["nearby"]),
                         ("C:/elsewhere/Hero.h does not exist.", []),
                         "the nearest folder that exists is the drive, and a walk of it could take seconds")

    def test_a_missing_search_folder_names_the_nearest_that_exists(self):
        ctx = context({CWD / "Source" / "a.h": b"x"})
        found = results(failed("Glob", {"pattern": "*.h", "path": str(CWD / "Source" / "Gone" / "Deeper")},
                               "Directory does not exist: Source/Gone/Deeper.", ctx), "diagnose.failure")[0]
        self.assertEqual((found.code, found.evidence["nearest"]), (Code.PATH_NOT_FOUND, "C:/game/Source"),
                         "a folder that is gone is answered with the nearest one that exists")

    def test_the_session_folder_is_named_as_the_current_folder(self):
        found = results(failed("Glob", {"pattern": "*.h", "path": str(CWD / "gone")},
                               "Directory does not exist: gone.", context({CWD / "a.h": b"x"})),
                        "diagnose.failure")[0]
        self.assertIn("The nearest folder that does is the current folder.", found.message,
                      "the session's own folder is named in words, never as a dot")

    def test_a_search_that_timed_out_is_too_broad(self):
        error = "Ripgrep search timed out after 20 seconds. The search may have matched files."
        found = results(failed("Glob", {"pattern": "**/*.h", "path": "C:/"}, error, context()),
                        "diagnose.failure")[0]
        self.assertEqual(found.code, Code.SEARCH_TOO_BROAD, "a timeout asks for a narrower search")

    def test_a_lock_is_left_to_write_locks(self):
        outcome = failed("Edit", {"file_path": str(CWD / "a.cpp"), "old_string": "a", "new_string": "b"},
                         "EPERM: operation not permitted, rename 'a' -> 'b'", context())
        self.assertEqual(results(outcome, "diagnose.failure"), [], "write.locks names the holder")


if __name__ == "__main__":
    unittest.main()
