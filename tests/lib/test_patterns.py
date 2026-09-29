"""A regex from a project file runs on every line of output, so one that could backtrack for seconds, that is
long, or that does not compile is named before it runs."""
import unittest

from ioguard.lib import patterns


class ARepeatedGroupThatRepeatsIsRefused(unittest.TestCase):
    def test_nested_repetition_is_found_past_classes_and_escapes(self):
        for pattern, nested in (("(a+)+", True), ("(?:\\w+\\s?)*$", True), ("((ab)*c)+", True),
                                ("(x{2,})+", True), ("(a+){3}", True), ("^ERROR: .*", False),
                                ("(ab)+", False), ("[(+)]+", False), ("\\(a+\\)+", False), ("(a+)?", False),
                                ("(a{1})+", False)):
            with self.subTest(pattern=pattern):
                self.assertEqual(patterns.nested(pattern), nested,
                                 "a quantified group whose text holds *, + or a count past one")

    def test_overlapping_choices_or_many_open_repeats_are_refused(self):
        for pattern, refused in (("(a|aa)+b", True), ("(?:x|y)*z", True),
                                 ("\\d+\\d+\\d+\\d+\\d+\\d+X", True), (".*a.*a.*a.*b", True),
                                 ("^Log\\w+: Error: .*", False),
                                 ("^(?:warning|error) C\\d+:", False)):
            with self.subTest(pattern=pattern):
                self.assertEqual(patterns.problem(pattern) is not None, refused,
                                 "a repeated choice, or over two open repeats, can backtrack for seconds")

    def test_the_problem_names_why(self):
        for pattern, words in (("(a+)+", "repeats a group"), ("(", "does not compile"),
                               ("a" * 201, "longer than 200")):
            with self.subTest(pattern=pattern[:10]):
                self.assertIn(words, patterns.problem(pattern), "one sentence says what is wrong")
        self.assertIsNone(patterns.problem("^LogTemp: Display:"), "a plain pattern passes")

    def test_every_string_in_a_value_is_checked(self):
        self.assertEqual(patterns.leaves({"a": ["x", "y"], "b": ["z"]}), ["x", "y", "z"],
                         "the strings of a mapping of lists, in order")


if __name__ == "__main__":
    unittest.main()
