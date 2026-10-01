"""lib.shell reads a Bash command as bash does: heredocs, python -c bodies, and the backslash pairs whose
halving changes what bash reads. A moved command runs the same as the original."""
import subprocess
import sys
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib import shell
from ioguard.lib.context import Context
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from tests.support import events, shells
from tests.support.project import TemporaryProject

BASH = shells.bash()
PYTHON = Path(sys.executable).as_posix()


def only_heredoc(command: str) -> shell.Heredoc:
    found = shell.scan(command).heredocs
    assert len(found) == 1, found
    return found[0]


class HeredocsAreFound(unittest.TestCase):
    def test_every_quoting_of_the_delimiter_means_no_expansion(self):
        for operator in ("<<'PY'", '<<"PY"', "<<\\PY", "<< 'PY'", "<<P'Y'"):
            with self.subTest(operator=operator):
                heredoc = only_heredoc(f"python - {operator}\nprint(1)\nPY\n")
                self.assertEqual((heredoc.quoted, heredoc.terminated, heredoc.body),
                                 (True, True, "print(1)\n"),
                                 "any quote in the word makes the body literal, and the body is read whole")

    def test_an_unquoted_delimiter_expands(self):
        heredoc = only_heredoc("cat <<EOF\nhello $HOME\nEOF")
        self.assertEqual((heredoc.quoted, heredoc.body), (False, "hello $HOME\n"),
                         "bash expands this body, so it is marked unquoted")

    def test_a_dash_strips_leading_tabs_from_the_body_and_the_delimiter(self):
        heredoc = only_heredoc("cat <<-'EOF'\n\tone\n\t\ttwo\n\tEOF\n")
        self.assertEqual((heredoc.body, heredoc.terminated), ("one\ntwo\n", True),
                         "<<- drops the leading tabs, as bash does")

    def test_two_heredocs_on_one_line_read_in_order(self):
        found = shell.scan("paste <<A <<'B'\none\nA\ntwo\nB\necho done").heredocs
        self.assertEqual([(heredoc.delimiter, heredoc.body) for heredoc in found],
                         [("A", "one\n"), ("B", "two\n")], "the second body starts after the first delimiter")

    def test_a_heredoc_inside_command_substitution_in_double_quotes(self):
        heredoc = only_heredoc("git commit -m \"$(cat <<'EOF'\nsubject\nEOF\n)\"")
        self.assertEqual(heredoc.body, "subject\n", "the commit-message shape is a heredoc too")

    def test_text_that_only_looks_like_a_heredoc_is_not_one(self):
        for command in ('echo "a << b"', "echo 'a << b'", "x=$((1 << 2))", "cat <<<word", "# <<EOF\nls"):
            with self.subTest(command=command):
                self.assertEqual(shell.scan(command).heredocs, (), "quotes, arithmetic, here-strings and "
                                                                   "comments hold no heredoc")

    def test_a_shift_inside_an_arithmetic_command_is_not_a_heredoc(self):
        for command in ("(( 1 << 2 ))\nsed -i s/a/b/ f", "for (( i = 1 << 2; i < 9; i++ )); do ls; done"):
            with self.subTest(command=command):
                self.assertEqual(shell.scan(command).heredocs, (), "bash reads (( )) as arithmetic")

    def test_a_dollar_quoted_delimiter_is_read_as_bash_reads_it(self):
        for operator in ("<<$'EOF'", '<<$"EOF"'):
            with self.subTest(operator=operator):
                heredoc = only_heredoc(f"cat {operator}\nx\nEOF\nls")
                self.assertEqual((heredoc.delimiter, heredoc.terminated, heredoc.body), ("EOF", True, "x\n"),
                                 "the $ of $'...' is quoting, not part of the delimiter")

    def test_command_substitution_nested_past_the_limit_is_marked_too_deep(self):
        for depth, deep in ((shell.MAX_NESTING, False), (1000, True), (600, True)):
            with self.subTest(depth=depth):
                for opening in ("$(", '"$('):
                    command = opening * depth + "true" + ")" * depth + "; ls"
                    self.assertEqual(shell.scan(command).too_deep, deep,
                                     "the scanner reads MAX_NESTING levels and marks a deeper command, never "
                                     "running out of stack")

    def test_a_body_with_no_delimiter_line_is_unterminated(self):
        self.assertFalse(only_heredoc("cat <<'EOF'\none\n").terminated, "a missing delimiter is marked")


class HalvingHazards(unittest.TestCase):
    def hazards(self, command: str) -> int:
        return len(shell.scan(command).hazards)

    def test_a_pair_bash_reads_differently_after_halving_is_a_hazard(self):
        for command in (r"sed 's/\\n/x/' f", r"cp C:\\a b", r"echo $'a\\n'", r'echo "a\\$x"',
                        "python - <<'PY'\nprint(r\"\\\\n\")\nPY\n"):
            with self.subTest(command=command):
                self.assertEqual(self.hazards(command), 1, "the halved command reads differently")

    def test_a_pair_bash_reads_the_same_either_way_is_not(self):
        for command in (r'echo "C:\\Users"', "cat <<EOF\n\\\\n\nEOF\n", r"# a \\ comment", r"echo a\b"):
            with self.subTest(command=command):
                self.assertEqual(self.hazards(command), 0,
                                 "double quotes and an expanding body read \\\\x and \\x the same")

    def test_every_pair_in_a_run_counts(self):
        self.assertEqual(self.hazards(r"echo 'a\\\\b'"), 2, "four backslashes are two pairs")

    def test_a_run_before_a_double_quote_arrives_whole(self):
        for command in ("cat <<'EOF'\np.split(\"\\\\\")\nEOF\n", r"""printf '%s' 'a\\"b'""",
                        r'echo "{\\\"k\\\": 1}"', "cat <<'EOF'\nB\\\\\\\\\"\nEOF\n"):
            with self.subTest(command=command):
                self.assertEqual(self.hazards(command), 0,
                                 "measured on 2.1.281: backslashes before a double quote are not halved")


class InlineBodiesAreFound(unittest.TestCase):
    def body(self, command: str) -> shell.InlineBody | None:
        found = shell.scan(command).bodies
        return found[0] if found else None

    def test_single_and_double_quoted_python_c(self):
        self.assertEqual(self.body("python -c 'print(1)'").body, "print(1)",
                         "a single-quoted body is literal")
        double = self.body('python3 -u -c "print(\\"x\\")" arg')
        self.assertEqual((double.body, double.expands), ('print("x")', False),
                         "a double-quoted body loses bash's escapes")

    def test_a_body_with_a_dollar_or_backtick_expands(self):
        self.assertTrue(self.body('python -c "print($HOME)"').expands, "bash expands $ in double quotes")

    def test_programs_by_path_and_after_assignments(self):
        for command in ("/c/Python314/python.exe -c 'x'", "PYTHONUTF8=1 python -c 'x'", "ls && py -3 -c 'x'",
                        '"C:/Python314/python.exe" -c \'x\''):
            with self.subTest(command=command):
                self.assertIsNotNone(self.body(command), "the program is found where a command starts")

    def test_a_body_behind_option_values_and_grouped_flags(self):
        for command in ("python -X utf8 -c 'x'", "python -W ignore -u -c 'x'", "python -Bc 'x'",
                        "python3 -X dev -W error::DeprecationWarning -Ic 'x'"):
            with self.subTest(command=command):
                self.assertEqual(self.body(command).body, "x",
                                 "-X and -W take a value, and -c may close a group of flags")

    def test_what_is_not_one_whole_quoted_body(self):
        for command in ("python -c 'a'\"b\"", "echo \"python -c 'x'\"", "python -c code", "mypython -c 'x'"):
            with self.subTest(command=command):
                self.assertIsNone(self.body(command), "a mixed word, a quoted mention or a bare word is left")


class SimpleCommandsAreSplitOut(unittest.TestCase):
    def test_commands_split_at_operators_outside_quotes(self):
        found = shell.commands("a 'x;y' && b \"p|q\" | c; d\ne")
        self.assertEqual([command.words for command in found],
                         [("a", "x;y"), ("b", "p|q"), ("c",), ("d",), ("e",)], "quotes keep their operators")

    def test_a_file_redirect_is_kept_and_a_stream_duplicate_is_not(self):
        found = shell.commands("make > build.log 2>&1 &> all.log >> more.log 2>/dev/null")[0]
        self.assertEqual([(redirect.target, redirect.append, redirect.fd) for redirect in found.redirects],
                         [("build.log", False, 1), ("all.log", False, None), ("more.log", True, 1),
                          ("/dev/null", False, 2)], "2>&1 names a stream, the rest name files")

    def test_assignments_and_reserved_words_do_not_name_the_command(self):
        found = shell.commands("if FOO=1 /usr/bin/python.exe x.py; then echo ok; fi")
        self.assertEqual([command.name for command in found], ["python", "echo"],
                         "the program's name is the first real word, without folder or .exe")

    def test_a_heredoc_body_and_a_comment_hold_no_command(self):
        found = shell.commands("cat <<'EOF' | wc -l\nrm -rf /\nEOF\n# echo x > y")
        self.assertEqual([command.words for command in found], [("cat",), ("wc", "-l")],
                         "the body's text and the comment are not commands")

    def test_a_backslash_before_a_newline_joins_the_lines(self):
        for command, words in (("git \\\npush origin", ("git", "push", "origin")),
                               ("gi\\\nt push", ("git", "push")), ('echo "a\\\nb"', ("echo", "ab"))):
            with self.subTest(command=command):
                self.assertEqual([found.words for found in shell.commands(command)], [words],
                                 "bash drops a backslash and the newline after it, outside single quotes")

    def test_a_command_substitution_stays_in_its_word(self):
        found = shell.commands('echo "$(date; ls > x)" > out.txt')
        self.assertEqual((len(found), found[0].redirects[0].target), (1, "out.txt"),
                         "the substitution is one word, and the outer redirect is the command's")


class AnInterpretersScriptFileIsNamed(unittest.TestCase):
    def test_the_script_and_its_arguments_past_the_interpreters_flags(self):
        cases = {"python -u -X utf8 fmt.py --apply a.cpp": ("fmt.py", ("--apply", "a.cpp")),
                 "py -3 tools/x.py": ("tools/x.py", ()), "node build.js": ("build.js", ()),
                 "python -m pytest": None, "python -c 'print(1)'": None, "python - < x.py": None,
                 "perl -e 'print 1'": None, "python": None, "make x.py": None}
        for command, expected in cases.items():
            with self.subTest(command=command):
                run = shell.script_run(shell.commands(command)[0])
                self.assertEqual(None if run is None else (run.script, run.arguments), expected,
                                 "a script file is the first word past the flags, and -c, -m or - run none")


class TheBudgetLength(unittest.TestCase):
    def test_bytes_and_apostrophes(self):
        self.assertEqual(shell.budget_length("a'b"), 6, "each apostrophe counts as four")
        self.assertEqual(shell.budget_length("za" + chr(0x17C)), 4, "a length is in UTF-8 bytes")


class BlankedKeepsOnlyCode(unittest.TestCase):
    def test_strings_comments_and_heredoc_bodies_become_spaces(self):
        command = "echo 'pkill x' \"$y\" # kill\ncat <<'E'\nbody\nE\nls"
        blanked = shell.blanked(command)
        self.assertEqual((len(blanked), blanked.count("\n"), "pkill" in blanked, "body" in blanked,
                          blanked.split()), (len(command), command.count("\n"), False, False,
                                             ["echo", "'", "'", '"', '"', "cat", "<<'E'", "ls"]),
                         "only code and the quote marks are left, at the offsets they had")


@unittest.skipIf(BASH is None, "no bash on this machine to run the commands")
class AMovedCommandRunsTheSame(unittest.TestCase):
    def run_bash(self, command: str, cwd: Path) -> bytes:
        """Run the command from a script file. On Windows an argument to bash -c crosses the same argv
        quoting that halves backslashes in the Bash tool, so it would not be the command as written."""
        script = cwd / "command.sh"
        script.write_bytes(command.encode("utf-8"))
        done = subprocess.run([BASH, str(script)], cwd=cwd, capture_output=True, timeout=60)
        self.assertEqual(done.returncode, 0, f"{BASH} ran the command: {done.stderr[-300:]!r}")
        return done.stdout + done.stderr

    def moved(self, command: str, folder: Path) -> str:
        found = shell.scan(command)
        heredocs, bodies = {}, {}
        for number, heredoc in enumerate(found.heredocs):
            path = folder / f"h{number}.txt"
            path.write_bytes(heredoc.body.encode("utf-8"))
            heredocs[heredoc] = path.as_posix()
        for number, body in enumerate(found.bodies):
            path = folder / f"b{number}.py"
            path.write_bytes(body.body.encode("utf-8"))
            bodies[body] = path.as_posix()
        return shell.moved(command, heredocs, bodies)

    def test_a_moved_heredoc_prints_the_same(self):
        script = ("import sys\nprint(sys.argv, repr(sys.path[0]), sys.stdin.read() == '')\n"
                  "print(len(r'\\\\n'))\n")
        command = f'"{PYTHON}" - a b <<\'PY\'\n{script}PY\necho after'
        with TemporaryProject() as root:
            rewritten = self.moved(command, root)
            self.assertNotIn("<<", rewritten, "the heredoc is gone from the command")
            self.assertEqual(self.run_bash(rewritten, root), self.run_bash(command, root),
                             "the moved command prints exactly what the original printed")

    def test_a_moved_python_c_prints_the_same(self):
        command = f"\"{PYTHON}\" -c 'import sys; print(sys.argv, repr(sys.path[0]), __name__)' a b"
        with TemporaryProject() as root:
            rewritten = self.moved(command, root)
            self.assertIn("exec(compile(open(", rewritten, "the body now runs from its file")
            self.assertEqual(self.run_bash(rewritten, root), self.run_bash(command, root),
                             "argv, sys.path[0] and __name__ are what -c gave the original")

    def test_everything_around_the_heredoc_stays_as_written(self):
        with TemporaryProject() as root:
            rewritten = self.moved("cat <<'EOF' | grep -c x\nx\ny\nx\nEOF\necho done", root)
        self.assertEqual(rewritten, f'cat < "{(root / "h0.txt").as_posix()}" | grep -c x\necho done',
                         "only the operator and the body change")


class PathsAreQuotedForBash(unittest.TestCase):
    def test_the_four_characters_bash_reads_in_double_quotes_are_escaped(self):
        self.assertEqual(shell.shell_path('a"b$c`d\\e'), '"a\\"b\\$c\\`d\\\\e"',
                         "the path arrives as written")


class ShapesBashReadsItsOwnWay(unittest.TestCase):
    def test_a_here_string_is_data_and_not_an_input_file(self):
        found = shell.commands('cat <<< "foo bar"; grep x <<<$y')
        self.assertEqual([(each.words, each.inputs) for each in found], [(("cat",), ()), (("grep", "x"), ())],
                         "<<< gives its word to stdin, and names no file and no argument")

    def test_a_python_c_body_after_a_wrapper_or_a_keyword_is_found(self):
        for command in ('time python -c "print(1)"', "if true; then python -c 'x=1'; fi",
                        "env FOO=1 python -c 'print(1)'", "for f in a; do python -c 'x=1'; done",
                        "exec python -c 'x=1'"):
            with self.subTest(command=command):
                self.assertEqual(len(shell.scan(command).bodies), 1, "the body is found and checked")

    def test_a_loop_head_is_named_for_its_keyword(self):
        for command, words in (("for f in /Game/a b; do echo $f; done", [("for", "f", "in", "/Game/a", "b"),
                                                                         ("echo", "$f")]),
                               ("for ((i=0;i<3;i++)); do echo $i; done", [("for", "((i=0;i<3;i++))"),
                                                                          ("echo", "$i")]),
                               ("select x in a b; do echo $x; done", [("select", "x", "in", "a", "b"),
                                                                      ("echo", "$x")])):
            with self.subTest(command=command):
                self.assertEqual([each.words for each in shell.commands(command)], words,
                                 "no program is named for the variable, and the values stay words, since "
                                 "each reaches the loop's commands")

    def test_a_case_pattern_inside_a_substitution_does_not_close_it(self):
        command = "echo $(case x in a) echo one;; esac) after"
        self.assertEqual([each.words for each in shell.commands(command)],
                         [("echo", "$(case x in a) echo one;; esac)", "after")],
                         "the pattern's ) belongs to the case, and the substitution closes at its own )")

    def test_a_quote_inside_a_parameter_expansion_keeps_the_string_whole(self):
        found = shell.scan('echo "${x:-"a b"}" done')
        self.assertEqual(([each.words for each in shell.commands('echo "${x:-"a b"}" done')],
                          found.unterminated), ([("echo", "${x:-a b}", "done")], False),
                         "bash reads one word, and the string closes after the }")
        self.assertEqual([shell.scan(text).unterminated for text in ("echo ${x", 'echo "${x', "echo ${x}")],
                         [True, True, False], "an expansion left open runs to the end, as bash reports")

    def test_a_quote_left_open_inside_a_substitution_ends_the_last_word(self):
        for command in ("""echo "$(conn x 'A < B)\"""", "echo $(a $'b", "echo \"$(a 'b"):
            with self.subTest(command=command):
                found = shell.commands(command)
                self.assertEqual((found[0].words[0], shell.scan(command).unterminated), ("echo", True),
                                 "the open quote runs to the end, and every offset stays inside the command")

    def test_a_command_inside_arithmetic_stays_visible(self):
        command = "echo $(( $(pgrep python) + 1 ))"
        self.assertIn("pgrep python", shell.blanked(command),
                      "only the arithmetic is hidden, not the command")


class ACommandIsScannedOnce(unittest.TestCase):
    def test_every_check_on_one_bash_call_shares_one_scan_and_one_split(self):
        command = f"echo {uuid.uuid4().hex} > out.txt && git status | grep -c M; python -c 'print(1)'"
        raw = events.bash(command, Path("C:/project"))
        event = Event.from_hook_json(raw, Surface.MCP_HOOK, Platform("win32", True))
        runs = {"scan": 0, "split": 0}
        real_run, real_split = shell.Scanner.run, shell.split

        def counted_run(scanner):
            runs["scan"] += 1
            return real_run(scanner)

        def counted_split(text):
            runs["split"] += 1
            return real_split(text)
        with mock.patch.object(shell.Scanner, "run", counted_run), mock.patch.object(shell, "split",
                                                                                   counted_split):
            Pipeline(default_registry()).run(event, Context.fake(platform=Platform("win32", True)))
        self.assertEqual(runs, {"scan": 1, "split": 1},
                         "the checks before a call read one scan and one list of simple commands")


class QuotingBashReadsDifferently(unittest.TestCase):
    def test_backticks_are_found_only_unescaped_inside_double_quotes(self):
        command = 'echo "a `b` \\`c\\`" \'`d`\' `e`'
        self.assertEqual([command[at] + command[at + 1] for at in shell.scan(command).backticks],
                         ["`b", "` "], "only the backticks bash runs inside double quotes count")

    def test_a_quote_left_open_is_unterminated(self):
        cases = ('ls "a', "ls 'a", "echo $'a", 'ls "a"', "", 'ls "a\\" && cat "b"', "echo 'a' \"")
        self.assertEqual([shell.scan(text).unterminated for text in cases],
                         [True, True, True, False, False, True, True],
                         "a command that ends inside a quote is unterminated, an empty one at the end too")

    def test_a_substitution_or_backtick_left_open_is_unterminated(self):
        cases = {"echo $(foo": True, "echo $(echo a # x)": True, "echo `foo": True, 'echo "`foo"': True,
                 "echo $(echo $(a)": True, "echo $(foo)": False, "echo `foo`": False, "echo \\`foo": False,
                 "echo '`' \"\\`\"": False, "echo $(echo ')')": False, "echo ${x}": False}
        self.assertEqual({text: shell.scan(text).unterminated for text in cases}, cases,
                         "bash stops at unexpected EOF on each open one, and on none that closes")

    def test_a_windows_path_ending_in_a_backslash_is_found_and_slashed(self):
        command = r'ls "C:\a b\c\" && cat "C:\d\e.md"'
        spans = shell.trailing_backslash_paths(command)
        self.assertEqual(shell.forward_slashed(command, spans), 'ls "C:/a b/c/" && cat "C:\\d\\e.md"',
                         "only the path whose last backslash escapes its quote changes")

    def test_an_ampersand_that_starts_a_command_is_a_call_operator(self):
        for command, expected in (('& "x.exe"', [0]), ("a && & b", [5]), ("a & b", []), ("x 2>&1", []),
                                  ("a &> log", []), ("a |& b", [])):
            with self.subTest(command=command):
                self.assertEqual(list(shell.call_operators(command, shell.scan(command).states)), expected,
                                 "only an & where a command starts is PowerShell's call operator")

    def test_a_pipe_is_told_from_an_or(self):
        command = "make | tail; a || b"
        piped = [shell.piped(command, simple) for simple in shell.commands(command)]
        self.assertEqual(piped, [True, False, False, False], "| pipes, || does not")

    def test_python_reads_its_program_from_stdin_only_without_a_script(self):
        cases = {"python -": True, "python3 -X utf8": True, "py -3 -": True, "python tool.py": False,
                 "python -c x": False, "python -m pytest": False, "cat": False}
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(shell.python_reads_stdin(shell.commands(command)[0]), expected,
                                 "a script, -c or -m means stdin is data")

    def test_the_carriage_return_quotes_git_bash_fails_to_parse_are_found(self):
        fails = [  # Git Bash 5.2.37 stopped on each on 2026-10-01, "unexpected EOF", the quote's line unrun
            r'''echo "F $(grep -c $'\r$' f) and $(grep -c $'\r$' f) end"''',
            r'''echo "$(echo a) $(echo $'\r')"''', r'''echo "$(echo $'\x0d') $(echo $'\x0d')"''',
            r'''echo "$(echo a) $(echo $'\015')"''', r'''echo "$(echo a) $(echo $'\15')"''',
            r'''echo "$(echo a) $(echo $'\cM')"''', r'''echo "$(echo a) $(echo $'\u000d')"''',
            r'''echo "$(echo a) $(echo $'\x0da')"''', r'''echo "$(echo a) $(echo $'\\r')"''',
            r'''echo "$(echo a) $(echo $'\\x0d')"''', r'''echo "$(echo a) $(echo b) $(echo $'\r')"''',
            r'''echo "$(echo a) $(echo $(echo $'\r'))"''', r'''echo "$(echo a) $( (echo $'\r') )"''',
            r'''echo "$(echo a) $(echo "$(echo $'\r')")"''',
            r'''echo "$(( $(echo 1) + $(printf $'\r' | wc -c) ))"''',
            r'''echo $(( $(echo 1) + $(printf $'\r' | wc -c) ))''',
            r'''printf "%s %s\n" "$(grep -c $'\r' f)" "$(( $(grep -c '' f) - $(grep -c $'\r' f) ))"''',
            r'''echo "$(echo a)"x"$(echo $'\r')"''', r'''echo $(echo a)"$(echo $'\r')"''',
            r'''echo "$(echo a)"$(echo $'\r')''', r'''echo $(echo a)$(echo $'\r')''',
            r'''echo "$(echo a)""$(echo $'\r')"''',
            "echo \"$(echo a) $(echo $'\\r')\"\necho x", "echo before\necho \"$(echo a) $(echo $'\\r')\"",
            "echo \"$(echo a) $(echo $'\\r'\n)\"", "echo \"$(echo a) $(echo $'\\r')\n\"",
        ]
        runs = [  # each ran in Git Bash 5.2.37 on 2026-10-01
            r'''echo "$(echo $'\r') $(echo a)"''', r'''echo "$(echo $'\t$') $(echo $'\t$')"''',
            r'''echo $(echo $'\r') $(echo $'\r')''', r'''echo "$(echo $'\r')" "$(echo $'\r')"''',
            r'''echo "$(echo $'\r' $'\r')"''', r'''echo "$(echo a) $(echo '\r')"''',
            r'''echo "$(echo a) $(echo $'\\t')"''', r'''echo "$(echo a) $(echo $'\\\\r')"''',
            r'''echo "$(echo a) $(echo $'r')"''', r'''echo "$(echo $(echo $'\r'))"''',
            r'''echo "$((1)) $(echo $'\r')"''', r'''echo "`echo a` $(echo $'\r')"''',
            r'''echo "$(( $(printf $'\r' | wc -c) + $(echo 1) ))"''',
            "echo \"$(echo a) $(echo b # it's\necho $'\\r')\"", "echo \"$(echo a)\n$(echo $'\\r')\"",
            "echo \"$(echo a) $(echo b\necho $'\\r')\"",
            r'''echo $(echo "$(echo a) $(echo $'\r')")''',
            r'''x=$(echo "$(echo a) $(echo $'\r')"); echo ok''',
            r'''echo "$(echo "$(echo a) $(echo $'\r')")"''',
        ]
        found = {command: [command[at:at + 2] for at in shell.scan(command).carriage_returns]
                 for command in fails + runs}
        self.assertEqual(found, {command: ["$'"] if command in fails else [] for command in fails + runs},
                         "each quote Git Bash failed on is found at its $', and none it ran")

    def test_moved_body_files_are_named(self):
        command = 'python - < "C:/s/io-guard/body-0123456789abcdef.txt"; cat /tmp/body-x.txt'
        self.assertEqual(shell.body_files(command), ("C:/s/io-guard/body-0123456789abcdef.txt",),
                         "only a file the move wrote is a body file")

    def test_a_long_token_is_searched_for_body_files_in_linear_time(self):
        started = time.perf_counter()
        found = shell.body_files("echo " + "a" * 100_000 + " x/io-guard/body-0123456789abcdef.py")
        self.assertEqual((found, time.perf_counter() - started < 0.5),
                         (("x/io-guard/body-0123456789abcdef.py",), True),
                         "a base64 blob in a command cannot stall the checks that look for body files")


def names(simples) -> list[str]:
    return [simple.name for simple in simples]


class ACommandIsNamedByItsFirstWords(unittest.TestCase):
    def test_an_entry_matches_by_its_first_words_without_case_folder_or_exe(self):
        for command, expected in (("make all", "make"), ('"C:/bin/MAKE.exe" all', "C:/bin/MAKE.exe"),
                                  ("git grep -n x", "git grep"), ("py -m pytest -q", "py -m pytest"),
                                  ("git log", None), ("maker", None)):
            with self.subTest(command=command):
                simple = shell.commands(command)[0]
                self.assertEqual(shell.matching(simple, ["make", "git grep", "python -m pytest"]), expected,
                                 "the label is the command's own words, and python matches py and python3")


class PipelinesAndTheExitCode(unittest.TestCase):
    def test_pipelines_are_joined_by_the_operator_before_them(self):
        lines = shell.pipelines("cd a && make 2>&1 | tail -5; grep x f || echo none")
        self.assertEqual([(line.joined_by, names(line.commands)) for line in lines],
                         [("", ["cd"]), ("&&", ["make", "tail"]), (";", ["grep"]), ("||", ["echo"])],
                         "a pipe joins commands into one pipeline, and the rest join pipelines")

    def test_the_exit_code_comes_from_the_and_chain_that_ends_the_command(self):
        for command, expected in (("cd a && grep -q x f && echo yes", ["echo", "grep", "cd"]),
                                  ("make; grep x log", ["grep"]), ("make || grep x log", ["grep"]),
                                  ("make | tail -3", ["tail"]),
                                  ("set -o pipefail; make | tail", ["tail", "make"]),
                                  ("for f in *.md; do grep -c x $f; done", ["grep"])):
            with self.subTest(command=command):
                self.assertEqual(names(shell.exit_candidates(command)), expected,
                                 "the last command of each pipeline an && joins can have set the exit code")

    def test_grouped_commands_leave_the_exit_code_unknown(self):
        for command in ("(cd a && make)", "if grep x f; then echo y; fi", "{ make; } && echo ok",
                        "! grep x f", "x=$(false) && grep a b", "grep a b; y=$(make)"):
            with self.subTest(command=command):
                self.assertIsNone(shell.pipelines(command), "the order alone no longer says what ran last")
                self.assertEqual(shell.exit_candidates(command), (), "so no command is named")

    def test_an_assignment_a_semicolon_ends_does_not_hide_the_order(self):
        command = "for f in $(ls | sort); do s=$(cat $f | wc -l); [ -n \"$s\" ] && echo $f; done"
        self.assertEqual(names(shell.exit_candidates(command)), ["echo", "["],
                         "pipes and parentheses inside $( ) belong to their word")


if __name__ == "__main__":
    unittest.main()
