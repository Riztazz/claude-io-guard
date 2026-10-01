"""readonly.only_reads tells a Bash command that can change no file from one that can."""
import unittest

from ioguard.lib import readonly


class ACommandThatOnlyReads(unittest.TestCase):
    def test_readers_and_the_shapes_around_them_only_read(self):
        for command in ("ls -la", "git log --oneline -3", "git -C sub --no-pager status --short",
                        "grep -n x f | head -5", "cat a > /dev/null 2>&1", "echo hi >&2",
                        'for f in *.md; do wc -l "$f"; done', "sed -n '1,5p' f", "find . -name '*.py'",
                        "diff <(sort a) <(sort b)", "X=1; echo $X", "cd src && ls; pwd", "echo '$(rm a)'"):
            with self.subTest(command=command):
                self.assertTrue(readonly.only_reads(command, readonly.READERS),
                                "every program only reads, and nothing goes to a file")

    def test_a_write_anywhere_in_the_command_can_change_a_file(self):
        for command in ("ls > out.txt", "ls; rm x", "X=$(rm a) && ls", "echo `rm b`", 'echo "$(rm a)"',
                        "cat <<EOF\n$(rm z)\nEOF", "sed -i 's/a/b/' f", "sed --in-place=.bak 's/a/b/' f",
                        "sed -n 'w out' f", "sed 's/a/b/w out' f", "sed '1e date' f", "find . -delete",
                        "find . -name x -exec rm {} +", "sort -o out f", "uniq in out",
                        "git diff --output=d.txt", "git checkout main", "git branch -D x", "python x.py",
                        "timeout 5 rm d",
                        "xargs rm < list", "env A=1 rm h", "grep x f | tee out", "", "ls\x00"):
            with self.subTest(command=command):
                self.assertFalse(readonly.only_reads(command, readonly.READERS),
                                 "a program that writes, a redirect, or a command bash runs unseen")

    def test_a_projects_list_replaces_the_readers(self):
        self.assertFalse(readonly.only_reads("cat a", ["ls"]), "the list names every program that only reads")
        self.assertTrue(readonly.only_reads("make -n", ["make -n"]), "an entry can name its first words")


if __name__ == "__main__":
    unittest.main()
