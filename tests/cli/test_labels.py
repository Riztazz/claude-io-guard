"""The corpus labels a recorded call with the baseline's rules: shell results, command shapes, file errors."""
import unittest

from ioguard.cli.labels import labels

BACKSLASH = chr(92)


class ShellCallsGetResultAndShapeLabels(unittest.TestCase):
    def test_each_seed_label_matches_the_output_it_counts(self):
        cases = {
            "unexpected-eof": "bash: -c: line 3: unexpected EOF while looking for matching `''",
            "hook-refused": "PreToolUse:Bash hook error: [python guard.py]: this command was refused",
            "msys-path": "error: C:/Program Files/Git/usr/bin/foo not found",
            "heredoc-eof": "warning: here-document at line 1 delimited by end-of-file (wanted `PY')",
        }
        for label, output in cases.items():
            with self.subTest(label=label):
                self.assertIn(label, labels("Bash", "echo", output, True), f"{label} is found in its output")

    def test_a_guards_file_name_in_output_is_not_a_refusal(self):
        self.assertEqual(labels("Bash", "wc -l *", "   74 write-guard.py", False), (),
                         "only a hook's refusal counts, never a guard's name in a listing or a diff")

    def test_a_command_shape_gets_a_cmd_label(self):
        self.assertEqual(labels("Bash", "python - <<'PY'\nprint(1)\nPY", "1", False), ("cmd-heredoc",),
                         "a heredoc command is tagged by its shape, even when it ran")

    def test_bytes_the_write_tool_cannot_carry_are_built_from_code_points(self):
        self.assertIn("bom", labels("Bash", "cat a", chr(0xFEFF) + "text", False),
                      "a real BOM character counts")
        self.assertIn("bom", labels("Bash", "cat a", BACKSLASH + "ufeff", False), "and so does its escape")
        self.assertIn("null-bytes", labels("Bash", "cat a", "a" + chr(0) + "b", False), "a NUL counts")

    def test_a_drive_path_with_its_backslashes_eaten_is_labelled(self):
        self.assertIn("backslash-path", labels("Bash", "ls", "ls: cannot access C:Usersmeproj", True),
                      "C:Users glued to the next name is a path whose separators were lost")
        intact = "C:" + BACKSLASH + "Users" + BACKSLASH + "me"
        self.assertNotIn("backslash-path", labels("Bash", "ls", intact, True),
                         "an intact Windows path is not")


class FileToolsGetTheirErrorClass(unittest.TestCase):
    def test_a_failed_edit_gets_one_error_class(self):
        self.assertEqual(labels("Edit", "", "<tool_use_error>String to replace not found in file.", True),
                         ("not-found",), "the anchor miss is the baseline's not-found class")

    def test_an_error_no_rule_knows_is_other(self):
        self.assertEqual(labels("Write", "", "something odd", True), ("other",), "an unknown error is other")

    def test_a_file_call_that_ran_has_no_label(self):
        self.assertEqual(labels("Read", "", "1\tone", False), (),
                         "a successful file call has nothing to count")


if __name__ == "__main__":
    unittest.main()
