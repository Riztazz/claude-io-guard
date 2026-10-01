"""lib.portable finds the bash 4 syntax and the GNU-only options that macOS's bash 3.2 and BSD tools read
another way, where bash reads them, and leaves the portable forms alone."""
import unittest

from ioguard.lib import portable, shell


def bash4(command: str) -> list[str]:
    found = shell.scan(command)
    return [each.what for each in portable.bash4(command, found.states, shell.commands(command))]


def gnu(command: str) -> list[str]:
    return [each.what for each in portable.gnu_only(shell.commands(command))]


class Bash4SyntaxIsFound(unittest.TestCase):
    def test_each_construct_bash_32_lacks(self):
        cases = {"readarray -t lines < f": "readarray", "mapfile lines < f": "mapfile",
                 'echo "${name,,}"': "the case change", "echo ${name^^}": "the case change",
                 "declare -A seen": "declare -A, an associative array", "make |& tee log": "|&",
                 "make &>> log": "&>>", "shopt -s globstar": "globstar",
                 "echo ${a[-1]}": "a negative array index", "echo ${x@Q}": "the ${var@...} transform",
                 "wait -n": "wait -n"}
        for command, what in cases.items():
            with self.subTest(command=command):
                self.assertEqual(bash4(command), [what], "bash 3.2 lacks it")

    def test_the_same_text_in_single_quotes_or_portable_forms_is_left_alone(self):
        for command in ("echo '${name,,}'", "echo ${name}", "declare -a list", "make 2>&1 | tee log",
                        'grep "Cmd\\|&Inv" f.cpp',
                        "while IFS= read -r line; do echo $line; done < f"):
            with self.subTest(command=command):
                self.assertEqual(bash4(command), [], "bash does not read it, or bash 3.2 has it")


class GnuOnlyOptionsAreFound(unittest.TestCase):
    def test_each_option_bsd_tools_read_another_way(self):
        cases = {"sed -i 's/a/b/' f": "sed -i with no suffix",
                 "sed --in-place 's/a/b/' f": "sed -i with no suffix",
                 "grep -P '\\d+' f": "grep -P", "stat -c %s f": "stat -c", "date -d yesterday": "date -d",
                 "find . -printf '%p'": "find -printf", "cp -t out a b": "cp -t", "du -b f": "du -b",
                 "head -n -2 f": "head -n with a negative count"}
        for command, what in cases.items():
            with self.subTest(command=command):
                self.assertEqual(gnu(command), [what], "BSD's tool lacks it or reads it another way")

    def test_the_bsd_forms_pass(self):
        for command in ("sed -i '' 's/a/b/' f", "sed -i.bak 's/a/b/' f", "grep -E 'a+' f", "stat -f %z f",
                        "head -n 2 f", "cp a b out/"):
            with self.subTest(command=command):
                self.assertEqual(gnu(command), [], "a form both families read the same")

    def test_a_version_gives_its_major_number(self):
        self.assertEqual((portable.major("3.2.57"), portable.major("5.2.37"), portable.major(None)),
                         (3, 5, None), "the first number, or None when there is no version")


if __name__ == "__main__":
    unittest.main()
