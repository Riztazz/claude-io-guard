"""code_tokens reads a file as its code, so a comment pass compares equal and a code change does not, and
split_includes takes the include lines apart from the rest."""
import unittest

from ioguard.lib.code_tokens import compare

BOM = chr(0xFEFF)


class ACommentPassChangesNoCode(unittest.TestCase):
    CASES = {
        ".cpp": ("int a = 1; // old\n/* block\n   comment */\nint b = 2;\n",
                 "// new header\nint a = 1;   // new\nint b =\n    2;\n"),
        ".py": ('"""Old module doc."""\nx = 1  # old\n\n\ndef f():\n    """Old."""\n    return x\n',
                '"""New module doc,\nover two lines."""\nx = 1\n\ndef f():\n    """New."""\n    # a note\n'
                "    return x\n"),
        ".yml": ("a: 1 # old\nb: 2\n", "# header\na: 1\nb: 2 # new\n"),
        ".cs": ("using System; // old\nclass A {}\n",
                "using System;\n/// <summary>A.</summary>\nclass A {}\n"),
    }

    def test_comments_docstrings_and_layout_are_not_code(self):
        for suffix, (before, after) in self.CASES.items():
            with self.subTest(suffix=suffix):
                found = compare(before, after, suffix, "code")
                self.assertEqual((found.same, found.how), (True, "code"),
                                 "only comments, docstrings and layout changed, so the code is the same")

    def test_a_bom_is_not_code(self):
        self.assertTrue(compare(BOM + "int a;\n", "int a;\n", ".cpp", "code").same,
                        "a pass that drops a BOM changed no code")


class ACodeChangeIsFoundWhereItIs(unittest.TestCase):
    def test_a_changed_token_names_its_line_on_each_side(self):
        found = compare("// one\nint a = 1;\nint b = 2;\n", "int a = 1;\nint b = 3;\n", ".cpp", "code")
        self.assertEqual((found.same, found.before_line, found.after_line), (False, 3, 2),
                         "the 2 that became 3 is on line 3 before and line 2 after")

    def test_comment_markers_inside_strings_are_code(self):
        cases = [('char* s = "a // b";\n', 'char* s = "a // c";\n', ".cpp"),
                 ('auto r = R"(x */ y)";\n', 'auto r = R"(x */ z)";\n', ".cpp"),
                 ('url = "http://a"\n', 'url = "http://b"\n', ".py"),
                 ("echo '#1'\n", "echo '#2'\n", ".sh")]
        for before, after, suffix in cases:
            with self.subTest(before=before):
                self.assertFalse(compare(before, after, suffix, "code").same,
                                 "text after a comment marker inside a string is still code")

    def test_python_indentation_is_code(self):
        before = "if x:\n    a()\nb()\n"
        after = "if x:\n    a()\n    b()\n"
        self.assertFalse(compare(before, after, ".py", "code").same,
                         "moving b() into the if block changes what runs")

    def test_a_python_string_that_is_not_a_docstring_is_code(self):
        self.assertFalse(compare('def f():\n    x = 1\n    "a"\n', 'def f():\n    x = 1\n    "b"\n', ".py",
                                 "code").same, "only the first statement of a block is a docstring")

    def test_python_that_does_not_tokenize_is_read_by_its_hash_comments(self):
        found = compare("x = (1  # old\n", "x = (1  # new\n", ".py", "code")
        self.assertEqual((found.same, found.how), (True, "code"), "an unclosed bracket still compares")


class AKindWithNoRulesComparesExactly(unittest.TestCase):
    def test_an_unknown_kind_compares_every_line(self):
        found = compare("a\nb\n", "a\nc\n", ".txt", "code")
        self.assertEqual((found.same, found.how, found.before_line, found.after_line), (False, "exact", 2, 2),
                         "a .txt file has no comment rules, so line 2 is where it differs")

    def test_a_file_that_ends_early_names_no_line_on_its_side(self):
        found = compare("a\nb\n", "a\n", ".txt", "exact")
        self.assertEqual((found.before_line, found.after_line), (2, 0), "0 marks the side that has ended")


class AnIncludePassComparesTheRest(unittest.TestCase):
    def test_sorted_includes_are_the_same_code(self):
        before = '#include "b.h"\n#include "a.h"\nint x;\n'
        after = '#include "a.h"\n#include "b.h"\nint x;\n'
        found = compare(before, after, ".cpp", "includes")
        self.assertEqual((found.same, found.added, found.removed), (True, (), ()),
                         "the same includes in another order, and the same code")

    def test_a_removed_include_is_named(self):
        found = compare('#include "a.h"\n#include "b.h"\nint x;\n', '#include "a.h"\nint x;\n', ".cpp",
                        "includes")
        self.assertEqual((found.same, found.removed), (False, ('#include "b.h"',)),
                         "the lost include is named")

    def test_a_code_change_beside_the_includes_is_found(self):
        found = compare("import os\nx = 1\n", "import sys\nimport os\nx = 2\n", ".py", "includes")
        self.assertEqual((found.same, found.before_line, found.after_line, found.added),
                         (False, 2, 3, ("import sys",)), "x = 1 became x = 2, and sys was added")


if __name__ == "__main__":
    unittest.main()
