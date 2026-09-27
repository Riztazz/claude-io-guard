"""CODES is one declaration, and every result renders as CODE: what happened. What to do."""
import unittest
from pathlib import Path

from ioguard.lib.results import CODES, Code, Fix, Result, Severity, render, render_many, spec


class CodesAreOneDeclaration(unittest.TestCase):
    def test_each_code_is_declared_once(self):
        names = [entry.code for entry in CODES]
        self.assertEqual(len(names), len(set(names)), "a code name appears in CODES once")

    def test_the_enum_is_generated_from_codes(self):
        self.assertEqual([code.value for code in Code], [entry.code for entry in CODES],
                         "the Code enum holds exactly the codes CODES declares, in order")

    def test_each_summary_and_fix_is_one_ascii_sentence(self):
        for entry in CODES:
            for text in (entry.summary, entry.fix):
                with self.subTest(code=entry.code, text=text):
                    self.assertTrue(text.isascii() and text.endswith(".") and text.count(". ") == 0,
                                    "a code's summary and fix are each one ASCII sentence")


class ResultsRender(unittest.TestCase):
    def test_a_result_renders_its_code_message_and_fix(self):
        result = Result.of(Code.REWRITE_CONFLICT, "Two fixes collided.", "Bash", "win32",
                           fix=Fix("Bash", {"command": "ls"}, "Run it again."))
        self.assertEqual(result.render(), "REWRITE_CONFLICT: Two fixes collided. Run it again.",
                         "a result renders as CODE: message, then the fix's text")

    def test_a_message_with_quoted_lines_puts_the_fix_on_its_own_line(self):
        result = Result.of(Code.STALE_VIEW, "Line 1 reads:\n1| x", "Edit", "win32")
        self.assertEqual(render(result), f"STALE_VIEW: Line 1 reads:\n1| x\n{spec(Code.STALE_VIEW).fix}",
                         "the fix never runs on from the last quoted line")

    def test_without_a_fix_the_codes_own_advice_follows(self):
        result = Result.of(Code.GUARD_ERROR, "A check failed.", "Edit", "darwin")
        self.assertEqual(render(result), f"GUARD_ERROR: A check failed. {spec(Code.GUARD_ERROR).fix}",
                         "with no fix, the code's general advice is the second sentence")

    def test_the_severity_comes_from_the_code(self):
        self.assertIs(Result.of(Code.BUDGET_EXCEEDED, "x.", "Bash", "win32").severity, Severity.WARNING,
                      "Result.of takes the severity CODES declares for the code")

    def test_to_json_has_the_documented_shape(self):
        result = Result.of(Code.GUARD_ERROR, "A check failed.", "Write", "win32", file=Path("C:/p/a.txt"),
                           severity=Severity.REFUSED, evidence={"eol": "crlf"})
        shape = result.to_json()
        self.assertEqual(sorted(shape), sorted(["ok", "code", "severity", "tool", "platform", "file",
                                                "message", "evidence", "fix", "auto_fixed"]),
                         "a result's JSON has the fields context.md documents")
        self.assertEqual((shape["ok"], shape["file"]), (False, "C:/p/a.txt"),
                         "a refused result is not ok, and its file uses forward slashes")

    def test_several_results_render_one_per_line(self):
        results = [Result.of(Code.GUARD_ERROR, "One.", "Bash", "win32"),
                   Result.of(Code.BUDGET_EXCEEDED, "Two.", "Bash", "win32")]
        self.assertEqual(len(render_many(results).splitlines()), 2, "render_many gives one line per result")


if __name__ == "__main__":
    unittest.main()
