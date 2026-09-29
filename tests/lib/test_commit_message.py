"""lib.commit_message finds where a git commit takes its message from, past git's own options and inside
short option clusters, and names what a policy forbids in it with its line."""
import unittest

from ioguard.lib.commit_message import Problem, Sources, problems, sources, subcommand


class TheMessageSourcesAreFound(unittest.TestCase):
    def test_each_way_of_giving_a_message(self):
        cases = {("git", "commit", "-m", "a", "-m", "b"): Sources(("a", "b"), ()),
                 ("git", "commit", "-am", "a"): Sources(("a",), ()),
                 ("git", "commit", "-mtext"): Sources(("text",), ()),
                 ("git", "commit", "--message=a", "--file", "m.txt"): Sources(("a",), ("m.txt",)),
                 ("git", "commit", "-F", "-"): Sources((), ("-",)),
                 ("git", "commit", "-C", "HEAD", "--amend"): Sources((), ()),
                 ("git", "commit", "-S", "-m", "a"): Sources(("a",), ())}
        for words, expected in cases.items():
            with self.subTest(words=words):
                self.assertEqual(sources(words), expected, "-m, --message, -F and --file, alone or clustered")

    def test_a_long_option_git_takes_by_its_start(self):
        cases = {("git", "commit", "--mess", "a"): Sources(("a",), ()),
                 ("git", "commit", "--me=a"): Sources(("a",), ()),
                 ("git", "commit", "--fil", "m.txt"): Sources((), ("m.txt",)),
                 ("git", "commit", "--fi=m.txt", "--m", "b"): Sources(("b",), ("m.txt",))}
        for words, expected in cases.items():
            with self.subTest(words=words):
                self.assertEqual(sources(words), expected, "git reads a unique start of --message or --file")

    def test_git_options_before_the_subcommand_are_skipped(self):
        self.assertEqual((subcommand(("git", "-C", "sub", "-c", "a=b", "commit")),
                          subcommand(("C:/Git/bin/git.exe", "--no-pager", "commit")), subcommand(("gitk",))),
                         (5, 2, None), "-C and -c take a value, and only git runs git")

    def test_anything_but_a_commit_has_no_message(self):
        for words in (("git", "status"), ("git",), ("echo", "commit"), ()):
            with self.subTest(words=words):
                self.assertIsNone(sources(words), "no message to check")


class APolicyNamesWhatItForbids(unittest.TestCase):
    def test_forbidden_text_matches_without_case_and_names_its_line(self):
        self.assertEqual(problems("feat: x\n\nco-authored-by: a", ["Co-Authored-By"], False),
                         (Problem("Co-Authored-By", 3),), "git reads trailers without case")

    def test_the_first_non_ascii_character_is_named_when_asked(self):
        message = "fix: a " + chr(0x2014) + " b"
        self.assertEqual((problems(message, [], True), problems(message, [], False)),
                         ((Problem("U+2014", 1),), ()), "ascii_only names the character and its line")


if __name__ == "__main__":
    unittest.main()
