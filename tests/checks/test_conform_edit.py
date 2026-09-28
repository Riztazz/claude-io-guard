"""conform.edit gives new_string the indent of the lines around the edit, and leaves the rest to the Edit
tool."""
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, Severity
from tests.support import events

CWD = Path("C:/project")
WINDOWS = Platform("win32", True)
REGISTRY = default_registry()


def context(data: bytes, **values) -> Context:
    config = Config(MappingProxyType({**defaults(REGISTRY.keys()).values, **values}))
    return Context.fake(files={CWD / "a.cpp": data}, config=config, platform=WINDOWS)


def edit(data: bytes, old: str, new: str, replace_all: bool = False, ctx: Context | None = None):
    event = Event.from_hook_json(events.edit(CWD / "a.cpp", old, new, CWD, replace_all), Surface.MCP_HOOK,
                                 WINDOWS)
    return Pipeline(REGISTRY).run(event, ctx or context(data))


def decided(outcome):
    return next(decision for decision in outcome.decisions if decision.check_id == "conform.edit")


class WhatTheToolHandlesItself(unittest.TestCase):
    def test_trailing_whitespace_and_crlf_pass_untouched(self):
        outcome = edit(b"one = 1\r\ntwo = 2\r\n", "one = 1", "one = ")
        self.assertEqual((outcome.verdict, outcome.rewrites), (Verdict.OBSERVE, ()),
                         "the Edit tool keeps a trailing space and the file's CRLF, so nothing is changed")

    def test_a_missing_or_repeated_match_or_replace_all_is_left_to_the_tool(self):
        data = b"{\n\tint a;\n\tint a;\n}\n"
        for old, replace_all in (("\tint b;", False), ("\tint a;", False), ("\tint a;", True)):
            with self.subTest(old=old, replace_all=replace_all):
                self.assertEqual(edit(data, old, "    int c;", replace_all).rewrites, (),
                                 "the tool fails or replaces as asked, with no single place to read")


class TheIndentFollowsTheLinesAround(unittest.TestCase):
    def test_spaces_become_tabs_beside_tabs(self):
        data = b"void f()\n{\n\tint a = 1;\n\tint b = 2;\n}\n"
        outcome = edit(data, "\tint b = 2;", "    int b = 2;\n    int c = 3;")
        self.assertEqual((outcome.tool_input["new_string"], outcome.rewrites[0].code),
                         ("\tint b = 2;\n\tint c = 3;", Code.INDENT_MISMATCH),
                         "four spaces are one tab where the file indents with tabs")

    def test_tabs_become_spaces_beside_spaces(self):
        data = b"def f():\n    a = 1\n    b = 2\n"
        outcome = edit(data, "    b = 2", "\tb = 3")
        self.assertEqual(outcome.tool_input["new_string"], "    b = 3", "one tab is the file's four spaces")

    def test_the_conversion_is_a_fixed_point(self):
        data = b"void f()\n{\n\tint a = 1;\n\tint b = 2;\n}\n"
        first = edit(data, "\tint b = 2;", "    int b = 2;").tool_input["new_string"]
        again = edit(data, "\tint b = 2;", first)
        self.assertEqual((again.verdict, again.rewrites), (Verdict.OBSERVE, ()), "tabs beside tabs stay")

    def test_a_mixed_new_string_is_a_warning(self):
        data = b"{\n\tint a;\n\tint b;\n}\n"
        decision = next(decision for decision in edit(data, "\tint b;", "\tint b;\n    int c;").decisions
                        if decision.check_id == "conform.edit")
        self.assertEqual((decision.results[0].code, decision.results[0].severity, decision.rewrite),
                         (Code.INDENT_MISMATCH, Severity.WARNING, None), "mixed input is not guessed at")


class ADroppedSpaceIsRefused(unittest.TestCase):
    BRANCHES = b"a = f(x.Place.Branch, 1);\r\nb = f(y.Place.Branch, 2);\r\n"

    def test_the_recorded_replace_all_is_refused_with_its_joined_lines_and_the_strings_to_send(self):
        outcome = edit(self.BRANCHES, ".Place.Branch, ", ".Place.Branch.ToInt(),", replace_all=True)
        result = decided(outcome).results[0]
        self.assertEqual((outcome.verdict, result.code, result.evidence["lines"]),
                         (Verdict.DENY, Code.SPACE_DROPPED, [1, 2]), "both matches go on after the space")
        self.assertIn("1| a = f(x.Place.Branch.ToInt(),1);", result.message, "the line as the Edit leaves it")
        self.assertEqual(dict(result.fix.input), {"old_string": ".Place.Branch, 1",
                                                  "new_string": ".Place.Branch.ToInt(), 1"},
                         "both strings end one character later, with the space kept")
        self.assertIn("one Edit for each character", result.fix.text, "1 and 2 follow, so one Edit each")

    def test_the_same_edit_sent_again_is_refused_again_and_the_longer_strings_run(self):
        ctx = context(self.BRANCHES)
        first = edit(self.BRANCHES, ".Place.Branch, ", ".Place.Branch,", replace_all=True, ctx=ctx)
        again = edit(self.BRANCHES, ".Place.Branch, ", ".Place.Branch,", replace_all=True, ctx=ctx)
        longer = edit(self.BRANCHES, ".Place.Branch, 1", ".Place.Branch,1", ctx=ctx)
        self.assertEqual((first.verdict, again.verdict, longer.verdict),
                         (Verdict.DENY, Verdict.DENY, Verdict.OBSERVE),
                         "a model that means to drop the space ends both strings one character later")

    def test_a_space_at_the_end_of_its_line_is_safe_to_lose(self):
        outcome = edit(b"a = f(x.Place.Branch, \n", ".Place.Branch, ", ".Place.Branch.ToInt(),")
        self.assertEqual(outcome.verdict, Verdict.OBSERVE, "nothing follows the space on its line")

    def test_a_recorded_deletion_that_would_join_two_lines_is_refused_with_the_old_string_to_send(self):
        data = (b'VERDICTS = {\n    "a": lambda s, n: seen(s),\n    "b": lambda s, n: note_left_alone(n),\n'
                b'    "c": lambda s, n: locked(n),\n}\n')
        old = '\n    "b": lambda s, n: note_left_alone(n),'
        result = decided(edit(data, old, "")).results[0]
        self.assertEqual((result.code, result.fix.input["old_string"]),
                         (Code.LINES_JOINED, '    "b": lambda s, n: note_left_alone(n),\n'),
                         "the same lines, ending with their line break, delete cleanly")
        self.assertIn('2|     "a": lambda s, n: seen(s),    "c": lambda s, n: locked(n),', result.message,
                      "the message shows the two entries joined, as the recorded Edit left them")
        self.assertEqual(edit(data, result.fix.input["old_string"], "").verdict, Verdict.OBSERVE,
                         "the old_string the fix names is not refused")

    def test_the_setting_turns_the_refusal_off(self):
        ctx = context(self.BRANCHES, **{"checks.conform.edit.space_dropped": False})
        outcome = edit(self.BRANCHES, ".Place.Branch, ", ".Place.Branch,", replace_all=True, ctx=ctx)
        self.assertEqual(outcome.verdict, Verdict.OBSERVE, "space_dropped false lets the Edit run")


if __name__ == "__main__":
    unittest.main()
