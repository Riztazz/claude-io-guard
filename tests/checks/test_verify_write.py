"""verify.write compares each written file with the file before the write, puts back a lost BOM or line
endings, and reports every other byte fault the write left."""
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.checks.verify_write import REREAD, listed
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.profile import profile
from ioguard.lib.results import Code, Severity
from tests.support import events
from tests.support.fixtures import FIXTURES_DIR

CWD = Path("C:/project")
CLAUDE = Path("C:/Users/u/.claude")
NOTE = CLAUDE / "projects" / "C--project" / "memory" / "report-after-each-task.md"
ASKED = ("---\nname: report-after-each-task\ndescription: At the end of every task, run tools/report.py\n"
         "metadata:\n  type: feedback\n---\n\nRun the report.\n")
KEPT = ('---\nname: report-after-each-task\ndescription: "At the end of every task, run tools/report.py"\n'
        "metadata:\n  node_type: memory\n  type: feedback\n  originSessionId: 7eeb509f\n"
        "  modified: 2026-09-28T13:13:15.600Z\n---\n\nRun the report.\n")
WINDOWS = Platform("win32", True)
REGISTRY = default_registry()
BOM = b"\xef\xbb\xbf"
ARROW = chr(0x2192).encode("utf-8")
TEXT_FIXTURES = ("bom-crlf.txt", "bom-lf.txt", "crlf.txt", "indent-both.cpp", "indent-space.cpp",
                 "indent-tab.cpp", "large-300k.txt", "lf.txt", "lone-cr.txt", "mixed.txt",
                 "no-final-newline.txt", "private-use.txt")


def config(conform: bool, **options) -> Config:
    values = {**defaults(REGISTRY.keys()).values, "checks.conform.write.enabled": conform,
              "checks.conform.edit.enabled": conform}
    values.update({f"checks.verify.write.{name}": value for name, value in options.items()})
    return Config(MappingProxyType(values))


def honest_edit(before: bytes, old: str, new: str) -> bytes:
    """The bytes the Edit tool leaves: the BOM kept, and new_string's line breaks in a CRLF file as CRLF."""
    bom = BOM if before.startswith(BOM) else b""
    text = before[len(bom):].decode("utf-8")
    if "\r\n" in text:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    return bom + text.replace(old, new, 1).encode("utf-8")


def call(tool: str, tool_input: dict, before: bytes | None, landed=None, name: str = "a.txt",
         conform: bool = False, path: Path | None = None, **options):
    """Run PreToolUse over before, leave landed on disk as the tool's result, then run PostToolUse. landed
    is bytes, or a function of the input the tool ran with and the bytes before. Returns the PostToolUse
    outcome and the context."""
    path = path or CWD / name
    ctx = Context.fake(files={} if before is None else {path: before}, config=config(conform, **options),
                       platform=WINDOWS, env={"CLAUDE_CONFIG_DIR": str(CLAUDE)})
    given = {"file_path": str(path), **tool_input}
    pre = Pipeline(REGISTRY).run(Event.from_hook_json(events.pre_tool_use(tool, given, CWD), Surface.MCP_HOOK,
                                                      WINDOWS), ctx)
    ctx.fs.files[path] = landed(pre.tool_input, before) if callable(landed) else landed
    post = Event.from_hook_json(events.post_tool_use(tool, given, {}, CWD), Surface.MCP_HOOK, WINDOWS)
    return Pipeline(REGISTRY).run(post, ctx), ctx


def results(outcome):
    return [result for decision in outcome.decisions if decision.check_id == "verify.write"
            for result in decision.results]


def codes(outcome) -> list[Code]:
    return [result.code for result in results(outcome)]


def fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def first_line(data: bytes) -> str:
    return data.removeprefix(BOM).decode("utf-8").replace("\r", "\n").split("\n")[0]


def last_line_start(data: bytes) -> int:
    body = data.rstrip(b"\r\n")
    return max(body.rfind(b"\n") + 1, len(BOM) if data.startswith(BOM) else 0)


def inserted(data: bytes, piece: bytes) -> bytes:
    at = last_line_start(data)
    return data[:at] + piece + data[at:]


FAULTS = {
    "control bytes": (lambda data: inserted(data, b"\x01\x00"), Code.CONTROL_BYTES_ADDED),
    "U+FFFD": (lambda data: inserted(data, chr(0xFFFD).encode("utf-8")), Code.ENCODING_INVALID),
    "not UTF-8": (lambda data: inserted(data, b"\xe9"), Code.ENCODING_INVALID),
    "non-ASCII": (lambda data: inserted(data, ARROW), Code.NON_ASCII_ADDED),
    "zero-width space": (lambda data: inserted(data, chr(0x200B).encode("utf-8")), Code.INVISIBLE_ADDED),
    "emptied": (lambda data: b"", Code.SIZE_COLLAPSED),
}


class EveryByteFaultIsReported(unittest.TestCase):
    def test_each_fault_injected_into_each_fixture_after_an_edit(self):
        for name in TEXT_FIXTURES:
            before = fixture(name)
            old = first_line(before)
            honest = honest_edit(before, old, old + "!")
            for fault, (inject, code) in FAULTS.items():
                with self.subTest(fixture=name, fault=fault):
                    outcome, _ = call("Edit", {"old_string": old, "new_string": old + "!"}, before,
                                      inject(honest), name=name, ascii_only=[".txt", ".cpp"])
                    self.assertIn(code, codes(outcome), f"{fault} after an Edit of {name} is reported")

    def test_an_honest_edit_of_each_fixture_reports_nothing(self):
        for name in TEXT_FIXTURES:
            before = fixture(name)
            old = first_line(before)
            with self.subTest(fixture=name):
                outcome, _ = call("Edit", {"old_string": old, "new_string": old + "!"}, before,
                                  honest_edit(before, old, old + "!"), name=name, ascii_only=[".txt", ".cpp"])
                self.assertEqual(codes(outcome), [], "an Edit that changed only what it asked for is quiet")

    def test_an_invisible_character_in_a_string_is_named_with_its_line(self):
        content = "import io\nraw = raw.lstrip('" + chr(0xFEFF) + "')\n"
        outcome, _ = call("Write", {"content": content}, None, content.encode("utf-8"), name="fix.py")
        found = [result for result in results(outcome) if result.code is Code.INVISIBLE_ADDED]
        self.assertEqual(len(found), 1, "task 39: the U+FEFF a JSON escape became is reported")
        self.assertIn("[U+FEFF] on line 2", found[0].message, "with the character and its line")
        self.assertIn("backslash doubled", found[0].fix.text, "and the way to write the escape instead")

    def test_an_allowed_character_and_a_files_own_bom_pass(self):
        spaced = "price: 5" + chr(0xA0) + "EUR\n"
        allowed, _ = call("Write", {"content": spaced}, None, spaced.encode("utf-8"), name="a.txt")
        self.assertIn(Code.INVISIBLE_ADDED, codes(allowed), "a no-break space is reported by default")
        config_allowed = Config(MappingProxyType({**config(False).values, "invisible_allowed": ["U+00A0"]}))
        ctx = Context.fake(config=config_allowed, platform=WINDOWS)
        given = {"file_path": str(CWD / "a.txt"), "content": spaced}
        pre = events.pre_tool_use("Write", given, CWD)
        Pipeline(REGISTRY).run(Event.from_hook_json(pre, Surface.MCP_HOOK, WINDOWS), ctx)
        ctx.fs.files[CWD / "a.txt"] = spaced.encode("utf-8")
        post = Pipeline(REGISTRY).run(Event.from_hook_json(events.post_tool_use("Write", given, {}, CWD),
                                                           Surface.MCP_HOOK, WINDOWS), ctx)
        self.assertNotIn(Code.INVISIBLE_ADDED, codes(post), "invisible_allowed lets U+00A0 through")
        bom, _ = call("Edit", {"old_string": "a", "new_string": "b"}, BOM + b"a\n", BOM + b"b\n")
        self.assertNotIn(Code.INVISIBLE_ADDED, codes(bom), "the BOM a file already had is not new text")

    def test_a_line_changed_outside_the_edit_is_named(self):
        before = b"one\ntwo\nthree\n"
        outcome, _ = call("Edit", {"old_string": "one", "new_string": "ONE"}, before, b"ONE\ntwo\nTHREE\n")
        found = results(outcome)
        self.assertEqual((found[0].code, found[0].evidence["lines"]), (Code.UNINTENDED_CHANGE, [3]),
                         "line 3 changed, and the Edit asked only for line 1")

    def test_a_change_inside_the_edited_lines_is_not_unintended(self):
        before = b"say('hi')\nend\n"
        landed = "say(" + chr(0x2018) + "yo" + chr(0x2019) + ")\nend\n"
        outcome, _ = call("Edit", {"old_string": "say('hi')", "new_string": "say('yo')"}, before,
                          landed.encode("utf-8"))
        self.assertNotIn(Code.UNINTENDED_CHANGE, codes(outcome),
                         "the tool may restyle quotes on the line it wrote, which the call asked to change")

    def test_a_new_indent_style_is_a_warning(self):
        before = fixture("indent-tab.cpp")
        landed = before.replace(b"\t", b"    ", 1)
        outcome, _ = call("Edit", {"old_string": "void f()", "new_string": "void g()"}, before,
                          landed.replace(b"void f()", b"void g()"), name="a.cpp")
        self.assertIn(Code.INDENT_MISMATCH, codes(outcome), "spaces in a tab-indented file are named")

    def test_bytes_a_legacy_code_page_lost_are_named(self):
        before = fixture("cp1250.txt")
        landed = before.decode("utf-8", "replace").encode("utf-8")
        outcome, _ = call("Write", {"content": landed.decode("utf-8")}, before, landed)
        self.assertEqual(codes(outcome), [Code.ENCODING_INVALID],
                         "cp1250 letters that came back as U+FFFD are data the write lost (BYT-6)")


class ALostBomOrEndingIsPutBack(unittest.TestCase):
    def test_a_write_that_dropped_both_is_repaired_and_says_to_read_again(self):
        before = BOM + b"one\r\ntwo\r\n"
        outcome, ctx = call("Write", {"content": "one\nthree\n"}, before, b"one\nthree\n")
        found = results(outcome)
        self.assertEqual((ctx.fs.files[CWD / "a.txt"], [result.code for result in found]),
                         (BOM + b"one\r\nthree\r\n", [Code.EOL_CONVERTED]),
                         "the file's CRLF and BOM go back on, as one fix")
        self.assertEqual((found[0].severity, found[0].fix.text, found[0].fix.tool),
                         (Severity.FIXED, REREAD, "Read"),
                         "a repair tells the agent to read the file before the next Edit")

    def test_a_repair_is_counted_in_telemetry(self):
        _, ctx = call("Write", {"content": "one\n"}, b"one\r\n", b"one\n")
        recorded = [(item.check, item.code, item.severity) for item in ctx.telemetry.events if item.check]
        self.assertIn(("verify.write", Code.EOL_CONVERTED.value, "fixed"), recorded,
                      "each repair is one telemetry line with its code and the fixed severity")

    def test_a_dropped_bom_alone_is_restored(self):
        outcome, ctx = call("Write", {"content": "one\n"}, BOM + b"one\n", b"one\n")
        self.assertEqual((codes(outcome), ctx.fs.files[CWD / "a.txt"]), ([Code.BOM_RESTORED], BOM + b"one\n"),
                         "only the BOM was lost, and only the BOM goes back")

    def test_with_repair_off_the_changes_are_reported_and_left(self):
        outcome, ctx = call("Write", {"content": "one\n"}, BOM + b"one\r\n", b"one\n", repair=False)
        self.assertEqual((codes(outcome), ctx.fs.files[CWD / "a.txt"]),
                         ([Code.EOL_MISMATCH, Code.BOM_CHANGED], b"one\n"), "no repair, two warnings")

    def test_each_single_style_fixture_gets_its_endings_back(self):
        for name in TEXT_FIXTURES:
            before = fixture(name)
            if profile(before).eol.value not in ("CRLF", "LF"):
                continue
            old = first_line(before)
            honest = honest_edit(before, old, old + "!")
            flipped = honest.replace(b"\r\n", b"\n") if b"\r\n" in honest else honest.replace(b"\n", b"\r\n")
            with self.subTest(fixture=name):
                outcome, ctx = call("Edit", {"old_string": old, "new_string": old + "!"}, before, flipped,
                                    name=name)
                self.assertEqual((codes(outcome)[:1], profile(ctx.fs.files[CWD / name]).eol),
                                 ([Code.EOL_CONVERTED], profile(before).eol),
                                 f"{name} gets its own endings back")


class TheSnapshotHoldsWhatTheToolRan(unittest.TestCase):
    def test_a_conformed_write_that_landed_as_conformed_is_quiet(self):
        before = BOM + b"one\r\ntwo\r\n"
        landed = lambda given, _: given["content"].encode("utf-8")
        outcome, ctx = call("Write", {"content": "one\nthree\n"}, before, landed, conform=True)
        self.assertEqual((codes(outcome), ctx.fs.writes), ([], []),
                         "the snapshot keeps the input after conform.write, so what landed is what was asked")

    def test_a_write_that_landed_differently_is_unintended(self):
        outcome, _ = call("Write", {"content": "a = 1\nb = 2\n"}, b"old\n", b"a = 1\nb=2\n")
        self.assertEqual(codes(outcome), [Code.UNINTENDED_CHANGE],
                         "a formatter after the write changed line 2")

    def test_a_read_file_keeps_the_profile_of_what_the_agent_wrote(self):
        ctx = Context.fake(files={CWD / "a.txt": b"one\r\n"}, config=config(False), platform=WINDOWS)
        ctx.session.read_profiles[CWD / "a.txt"] = profile(b"one\r\n")
        given = {"file_path": str(CWD / "a.txt"), "content": "two\n"}
        pre, post = events.pre_tool_use("Write", given, CWD), events.post_tool_use("Write", given, {}, CWD)
        Pipeline(REGISTRY).run(Event.from_hook_json(pre, Surface.MCP_HOOK, WINDOWS), ctx)
        ctx.fs.files[CWD / "a.txt"] = b"two\n"
        Pipeline(REGISTRY).run(Event.from_hook_json(post, Surface.MCP_HOOK, WINDOWS), ctx)
        self.assertEqual(ctx.session.read_profiles[CWD / "a.txt"].sha256, profile(b"two\r\n").sha256,
                         "the agent's own write, repaired to CRLF, is the profile a later command sees")

    def test_a_new_file_written_as_asked_is_quiet(self):
        outcome, _ = call("Write", {"content": "x\n"}, None, b"x\n")
        self.assertEqual(codes(outcome), [], "a new file has nothing before it to lose")

    def test_a_binary_file_is_left_alone(self):
        outcome, ctx = call("Write", {"content": "x\n"}, fixture("nul-byte.txt"), b"x\r\n")
        self.assertEqual((outcome.verdict, ctx.fs.writes), (Verdict.OBSERVE, []), "a binary file is not text")

    def test_a_large_file_is_compared_by_profile_only(self):
        before = b"line\r\n" * 10
        outcome, _ = call("Write", {"content": "line\n" * 10}, before, b"line\n" * 10, snapshot_bytes=10)
        self.assertEqual(codes(outcome), [Code.EOL_CONVERTED],
                         "past snapshot_bytes the endings still compare")

    def test_a_post_event_without_a_snapshot_or_after_a_failure_is_quiet(self):
        ctx = Context.fake(files={CWD / "a.txt": b"x\n"}, config=config(False), platform=WINDOWS)
        given = {"file_path": str(CWD / "a.txt"), "content": "y\n"}
        pre = events.pre_tool_use("Write", given, CWD)
        Pipeline(REGISTRY).run(Event.from_hook_json(pre, Surface.MCP_HOOK, WINDOWS), ctx)
        failed = events.post_tool_use_failure("Write", given, "File has been modified since read", CWD)
        Pipeline(REGISTRY).run(Event.from_hook_json(failed, Surface.MCP_HOOK, WINDOWS), ctx)
        ctx.fs.files[CWD / "a.txt"] = b""
        post = Pipeline(REGISTRY).run(Event.from_hook_json(events.post_tool_use("Write", given, {}, CWD),
                                                           Surface.MCP_HOOK, WINDOWS), ctx)
        self.assertEqual((ctx.session.snapshots, codes(post)), ({}, []),
                         "a failure discards the snapshot, and a result with none to compare says nothing")


class ClaudeCodesMemoryFrontmatterIsExpected(unittest.TestCase):
    def test_the_recorded_write_of_a_memory_note_is_quiet(self):
        outcome, _ = call("Write", {"content": ASKED}, None, KEPT.encode("ascii"), path=NOTE)
        self.assertEqual(codes(outcome), [], "Claude Code quoted the description and added three keys")

    def test_an_edit_of_a_notes_body_is_quiet_when_claude_code_moves_its_modified_time(self):
        later = KEPT.replace("13:13:15", "14:02:40").replace("Run the report.", "Run it.")
        outcome, _ = call("Edit", {"old_string": "Run the report.", "new_string": "Run it."},
                          KEPT.encode("ascii"), later.encode("ascii"), path=NOTE)
        self.assertEqual(codes(outcome), [], "modified: is the harness's, and the body is what was asked")

    def test_a_change_to_a_notes_body_is_still_named(self):
        landed = KEPT.replace("Run the report.", "Run the reports.").encode("ascii")
        found = results(call("Write", {"content": ASKED}, None, landed, path=NOTE)[0])
        self.assertEqual((found[0].code, found[0].evidence["lines"]), (Code.UNINTENDED_CHANGE, [11]),
                         "only the frontmatter is Claude Code's to rewrite")

    def test_the_same_change_outside_the_memory_folder_is_named(self):
        outcome, _ = call("Write", {"content": ASKED}, None, KEPT.encode("ascii"), name="notes.md")
        self.assertEqual(codes(outcome), [Code.UNINTENDED_CHANGE], "a project's own markdown is not a note")


class MessagesListLines(unittest.TestCase):
    def test_line_lists(self):
        self.assertEqual([listed((4,)), listed((4, 9)), listed(tuple(range(1, 13)))],
                         ["line 4", "lines 4 and 9", "lines 1, 2, 3, 4, 5 and 7 more"],
                         "one line, two lines, and a long list cut to five")


if __name__ == "__main__":
    unittest.main()
