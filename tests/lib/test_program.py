"""A command word's program name comes from one function, and every reader of a command word agrees on it."""
import re
import unittest

from ioguard.lib import commit_message, rules, shell, telemetry, telemetry_summary, writes
from ioguard.lib.program import PROGRAM_SUFFIXES, program_name
from tests import PLUGIN_SCRIPTS


class AWordNamesItsProgram(unittest.TestCase):
    def test_each_shape_of_a_word_gives_the_bare_name(self):
        cases = {"git": "git", "/usr/bin/git": "git", "C:\\Git\\cmd\\git.exe": "git",
                 "C:/Git/cmd/GIT.EXE": "git", "tools\\Build.Exe": "build", "run.cmd": "run.cmd", "": ""}
        for word, name in cases.items():
            with self.subTest(word=word):
                self.assertEqual(program_name(word), name,
                                 "the last segment on either separator, .exe off in any case, in lower case")

    def test_the_caller_picks_the_suffixes_and_the_case(self):
        self.assertEqual(program_name("C:\\Git\\cmd\\Git.CMD", PROGRAM_SUFFIXES), "git",
                         "a program suffix the caller names comes off in any case")
        self.assertEqual(program_name("C:/Git/cmd/Git.exe", (), fold=False), "Git.exe",
                         "with no suffixes and no folding only the folder comes off")

    def test_a_quoted_first_word_is_one_program_for_telemetry(self):
        self.assertEqual(telemetry.program_of('"C:/Program Files/Git/cmd/git.exe" push'), "git.exe",
                         "a quoted path with a space names one program")


class EveryReaderAgreesOnTheProgram(unittest.TestCase):
    def test_a_backslash_path_is_the_program_for_every_reader(self):
        self.assertEqual(writes.in_place(["C:\\tools\\sed.exe", "-i", "s/a/b/", "f.txt"]),
                         ("sed -i", ["f.txt"]), "sed -i run by its Windows path edits in place")
        self.assertEqual(writes.delegated(["C:\\tools\\find.exe", "src", "-exec", "sed", "-i", "s/a/b/", "{}",
                                           ";"])[2], "find -exec",
                         "find run by its Windows path runs its -exec command on each file")
        self.assertEqual(commit_message.subcommand(["C:\\Git\\cmd\\git.cmd", "commit", "-m", "x"]), 1,
                         "git run through git.cmd commits, as the permission rules read it")
        self.assertEqual(rules.named(["C:/Git/cmd/git.Exe", "push"]), ["git", "push"],
                         "a rule meets the program whatever the case of its suffix")
        self.assertEqual(shell.commands("C:\\\\Git\\\\cmd\\\\git.exe status")[0].name, "git",
                         "the shell parser names the same program")
        self.assertEqual(telemetry_summary.shape("C:\\Git\\cmd\\git.exe status"), "git.exe status",
                         "the report keeps the program as written, less its folder")

    def test_no_module_splits_a_command_word_by_hand(self):
        by_hand = re.compile(r're\.split\(r"\[\\\\/\]"|words\[0\]\.(?:replace|rsplit)|PurePath\(words\[0\]')
        found = [f"{path.relative_to(PLUGIN_SCRIPTS).as_posix()}:{number}"
                 for path in sorted((PLUGIN_SCRIPTS / "ioguard").rglob("*.py")) if path.name != "program.py"
                 for number, line in enumerate(path.read_bytes().decode("utf-8").splitlines(), 1)
                 if by_hand.search(line)]
        self.assertEqual(found, [], "a command word's program comes from lib.program, so the readers agree")


if __name__ == "__main__":
    unittest.main()
