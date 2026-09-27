"""conform.edit gives new_string the indent of the lines around the edit, and leaves the rest to the Edit
tool."""
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, Severity
from tests.support import events

CWD = Path("C:/project")
WINDOWS = Platform("win32", True)
REGISTRY = default_registry()


def edit(data: bytes, old: str, new: str, replace_all: bool = False):
    event = Event.from_hook_json(events.edit(CWD / "a.cpp", old, new, CWD, replace_all), Surface.MCP_HOOK,
                                 WINDOWS)
    ctx = Context.fake(files={event.file_path: data}, config=defaults(REGISTRY.keys()), platform=WINDOWS)
    return Pipeline(REGISTRY).run(event, ctx)


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


if __name__ == "__main__":
    unittest.main()
