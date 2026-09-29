"""shell.results says what a shell result means: an exit code that is an answer, the lines that report
errors, a pipe that hid them, a saved output, mojibake, a run after a failed build, and a command the Bash
tool cut."""
import unittest
from pathlib import Path
from types import MappingProxyType

from ioguard.checks.command_results import CommandResults
from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, Result, Severity
from tests.support import events

CWD = Path("C:/project")
WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)
CLAUDE = "C:/Users/u/.claude"
SAVED = Path(f"{CLAUDE}/projects/p/{events.SESSION_ID}/tool-results/b1.txt")
REGISTRY = Registry()
REGISTRY.register(CommandResults)
EOF = "Exit code 2\n/usr/bin/bash: -c: line 1: unexpected EOF while looking for matching `''"
COMPILER = "a.cpp(3): error C2065: 'x': undeclared identifier"


def context(files: dict | None = None, platform: Platform = WINDOWS, **options) -> Context:
    values = {**defaults(REGISTRY.keys()).values,
              **{f"checks.shell.results.{name}": value for name, value in options.items()}}
    return Context.fake(files or {}, config=Config(MappingProxyType(values)), platform=platform,
                        env={"CLAUDE_CONFIG_DIR": CLAUDE})


def run(raw: dict, ctx: Context | None = None):
    ctx = ctx or context()
    return Pipeline(REGISTRY).run(Event.from_hook_json(raw, Surface.MCP_HOOK, ctx.platform), ctx)


def found(raw: dict, ctx: Context | None = None) -> list[Result]:
    return [result for decision in run(raw, ctx).decisions for result in decision.results]


def codes(raw: dict, ctx: Context | None = None) -> list[Code]:
    return [result.code for result in found(raw, ctx)]


def failed(command: str, error: str, tool: str = "Bash") -> dict:
    return events.post_tool_use_failure(tool, {"command": command}, error, CWD)


def ran(command: str, stdout: str, tool: str = "Bash", **response) -> dict:
    return events.post_tool_use(tool, {"command": command}, {**events.bash_result(stdout), **response}, CWD)


def lines(count: int, last: str = "") -> str:
    return "".join(f"step {number}\n" for number in range(1, count + 1 - bool(last))) + last


class AnExitCodeThatIsAnAnswer(unittest.TestCase):
    def test_grep_that_stopped_an_and_chain_says_what_did_not_run(self):
        result = found(failed("cd src && grep -c TODO a.cpp && echo found", "Exit code 1\n0"))[0]
        self.assertEqual((result.code, result.severity, result.message),
                         (Code.EXIT_BENIGN, Severity.INFO, "Exit code 1 is the answer grep gives when no "
                          "line matches, not a failure. The commands after it in the && chain did not run."),
                         "the model learns the chain stopped at an answer, not at a broken step")
        self.assertIn("|| true", result.fix.text, "and how to let the chain go on")

    def test_a_last_diff_is_an_answer_with_nothing_to_fix(self):
        result = found(failed("diff a.txt b.txt", "Exit code 1\n1c1\n< a\n---\n> b"))[0]
        self.assertEqual((result.message, result.fix.text[:14]),
                         ("Exit code 1 is the answer diff gives when the inputs differ, not a failure.",
                          "Nothing to fix"), "a diff that differs did its job")

    def test_pytest_that_collects_nothing_is_an_answer(self):
        result = found(failed("python -m pytest -k absent", "Exit code 5\nno tests ran in 0.01s"))[0]
        self.assertIn("gives when it collects no test", result.message, "pytest documents exit code 5")

    def test_a_code_left_unlabelled_where_the_answer_is_not_certain(self):
        for command, error in (("grep -q x f && python run.py", "Exit code 1"),
                               ("grep x f", "Exit code 2\ngrep: f: No such file or directory"),
                               ("cd nope && grep x f",
                                "Exit code 1\nbash: cd: nope: No such file or directory"),
                               ("python gen.py; grep x out.txt",
                                "Exit code 1\nTraceback (most recent call last):\nValueError: x"),
                               ("(grep x f)", "Exit code 1")):
            with self.subTest(command=command, error=error):
                self.assertNotIn(Code.EXIT_BENIGN, codes(failed(command, error)),
                                 "a command that can fail quietly, another code, an error in the output or "
                                 "a group leaves the failure a failure")

    def test_a_projects_own_command_names_its_answers(self):
        ctx = context(benign_exits={"lint-check": {"3": "the files need formatting"}})
        result = found(failed("lint-check src", "Exit code 3"), ctx)[0]
        self.assertEqual(result.message, "Exit code 3 is the answer lint-check gives when the files need "
                                         "formatting, not a failure.", "the setting adds a command's codes")


class ErrorLinesAreCountedAndQuoted(unittest.TestCase):
    def test_a_long_failed_output_gets_its_error_lines_quoted(self):
        result = found(failed("make", "Exit code 2\n" + lines(60, COMPILER + "\n")))[0]
        self.assertEqual(result.code, Code.ERRORS_IN_OUTPUT, "the error sits deep in a long output")
        self.assertEqual(result.message, "The output has 1 line that reports errors (1 compiler), first:\n"
                                         f"60| {COMPILER}", "the count, the kind and the numbered line")

    def test_at_short_lines_the_model_reads_the_output_itself(self):
        for count, expected in ((50, []), (51, [Code.ERRORS_IN_OUTPUT])):
            with self.subTest(count=count):
                self.assertEqual(codes(failed("make", "Exit code 2\n" + lines(count, COMPILER))), expected,
                                 "a short output is left alone, and one line past short_lines is not")

    def test_a_search_of_a_log_raises_no_alarm(self):
        output = "".join(f"{number}:{COMPILER}\n" for number in range(80))
        self.assertEqual(codes(ran("grep -n error build.log | head -80", output)), [],
                         "a search quotes errors, it does not raise them (OUT-7)")

    def test_a_summary_line_that_quotes_an_error_word_raises_nothing(self):
        output = lines(80, "Build succeeded.\n    0 Warning(s)\n    0 Error(s)\nErrors: 0\n")
        self.assertEqual(codes(failed("msbuild App.sln", "Exit code 1\n" + output)), [],
                         "only a line that reports an error counts (OUT-7)")

    def test_a_projects_own_pattern_counts(self):
        ctx = context(error_patterns={"log": [r"^Log\w+: Error: "]})
        result = found(failed("run-tests", "Exit code 1\n" + lines(60, "LogCore: Error: boom\n")), ctx)[0]
        self.assertIn("(1 log)", result.message, "the kind is the setting's own name")

    def test_a_powershell_output_is_read_the_same_way(self):
        output = lines(60, "MethodInvocationException: Exception calling Open\n")
        self.assertEqual(codes(failed("./build.ps1", "Exit code 1\n" + output, "PowerShell")),
                         [Code.ERRORS_IN_OUTPUT], "PowerShell's exceptions are error lines too")


class APipeThatHidesAFailure(unittest.TestCase):
    def test_errors_before_a_filter_are_named_with_the_filters_exit_code(self):
        output = "Traceback (most recent call last):\n  File \"b.py\", line 1\nValueError: bad\n"
        result = found(ran("python build.py 2>&1 | tail -5", output))[0]
        self.assertEqual((result.code, result.message),
                         (Code.PIPE_HIDES_EXIT, "The output has 1 line that reports errors (1 exception), "
                                                "and exit code 0 is tail's, the last command of the pipe:\n"
                                                "3| ValueError: bad"),
                         "a short output still says the exit code is the filter's")

    def test_a_command_that_only_lists_and_prints_files_hides_nothing(self):
        command = "ls open; ls done | tail -5; cat done/$(ls done | grep '^96') | head -60"
        output = "a.md\nb.md\n    self.assertEqual(long, [])\nAssertionError: Lists differ\n"
        self.assertEqual(codes(ran(command, output)), [],
                         "ls lists names and cat prints a file, so an error line there is quoted, not raised")

    def test_an_exit_code_the_command_printed_before_the_pipe_hides_nothing(self):
        output = "exit 1\nFAIL: test_x (tests.a.B.test_x)\n"
        for command in ('python run.py > out.txt 2>&1; echo "exit $?"; grep FAIL out.txt | head',
                        "make; printf 'code %s\\n' $?; grep error log.txt | sort -u"):
            with self.subTest(command=command):
                self.assertNotIn(Code.PIPE_HIDES_EXIT, codes(ran(command, output)),
                                 "the output already holds the exit code that matters")
        self.assertIn(Code.PIPE_HIDES_EXIT, codes(ran("echo $?; python run.py 2>&1 | tail", output)),
                      "an echo of $? before the failing command prints another code, so the warning stays")

    def test_pipefail_and_a_failed_pipe_hide_nothing(self):
        output = "ValueError: bad\n"
        for raw in (ran("set -o pipefail; python build.py | tail", output),
                    failed("python build.py | tail", "Exit code 1\n" + output)):
            with self.subTest(command=raw["tool_input"]["command"]):
                self.assertNotIn(Code.PIPE_HIDES_EXIT, codes(raw), "the exit code shown is the real one")


class ASavedOutputIsShownByItsEnds(unittest.TestCase):
    def saved(self, tool: str = "Bash", **options):
        text = "".join(COMPILER + "\n" if number == 50 else f"line {number}\n" for number in range(1, 101))
        ctx = context({SAVED: text.encode("utf-8")}, **options)
        response = {"stdout": text[:300], "stderr": "", "interrupted": False, "isImage": False,
                    "persistedOutputPath": str(SAVED), "persistedOutputSize": len(text)}
        raw = events.post_tool_use(tool, {"command": "make"}, response, CWD)
        return run(raw, ctx), len(text)

    def test_the_output_is_replaced_by_its_first_and_last_lines_and_its_errors(self):
        outcome, size = self.saved()
        stdout = outcome.output_replacement["stdout"].split("\n")
        self.assertEqual(stdout[:2],
                         [f"[io-guard: the whole output is in {SAVED.as_posix()}]", "  1| line 1"],
                         "the path first, then the output numbered as the Read tool numbers it")
        self.assertIn(f" 50| {COMPILER}", stdout, "the error line between the ends is kept")
        self.assertEqual(stdout[-1], "100| line 100", "and the last line")
        results = [result for decision in outcome.decisions for result in decision.results]
        self.assertEqual(results[0].message, f"The output was {size / 1024:.1f} KB in 100 lines, so io-guard "
                                             f"shows its first 20 lines, the 1 line that reports errors and "
                                             f"its last 20.", "the context says what the view holds")
        self.assertEqual([result.code for result in results], [Code.OUTPUT_SAVED, Code.ERRORS_IN_OUTPUT],
                         "and the error lines are counted")

    def test_the_replacement_keeps_the_tools_shape_without_the_saved_file_fields(self):
        for tool in ("Bash", "PowerShell"):
            with self.subTest(tool=tool):
                outcome, _ = self.saved(tool)
                self.assertEqual(set(outcome.output_replacement),
                                 {"stdout", "stderr", "interrupted", "isImage"},
                                 "with persistedOutputPath kept, Claude Code shows only its 2 KB preview")

    def test_an_older_notice_in_stdout_names_the_file(self):
        stdout = f"<persisted-output>\nOutput too large (1KB). Full output saved to: {SAVED}\n\nPreview:\nx"
        outcome = run(ran("make", stdout), context({SAVED: b"one\ntwo\n"}))
        self.assertTrue(outcome.output_replacement["stdout"].endswith("1| one\n2| two"),
                        "the notice is enough to find the file")

    def test_only_a_file_in_this_sessions_tool_results_folder_is_read(self):
        session = f"{CLAUDE}/projects/p/{events.SESSION_ID}"
        for named in (Path("C:/Users/u/.ssh/id_rsa"),
                      Path(f"{session}/tool-results/../../../../../.ssh/id_rsa"),
                      Path(f"{CLAUDE}/projects/p/another-session/tool-results/b1.txt"),
                      Path(f"{session}/b1.txt")):
            ctx = context({named: b"-----BEGIN KEY-----\nsecret\n"})
            for stdout, extra in ((f"Output too large (1KB). Full output saved to: {named}", {}),
                                  ("x", {"persistedOutputPath": str(named), "persistedOutputSize": 30})):
                with self.subTest(named=named, persisted=bool(extra)):
                    outcome = run(ran("cat notes.md", stdout, **extra), ctx)
                    self.assertIsNone(outcome.output_replacement,
                                      "io-guard reads a saved output only where Claude Code saves this "
                                      "session's outputs")

    def test_a_file_that_is_gone_or_past_max_bytes_is_left_as_it_is(self):
        stdout = f"Output too large (1KB). Full output saved to: {SAVED}"
        self.assertIsNone(run(ran("make", stdout)).output_replacement, "no file, no view of it")
        outcome, _ = self.saved(max_bytes=100)
        self.assertIsNone(outcome.output_replacement, "a file past max_bytes is not read")


class MojibakeIsNamedWithTheFix(unittest.TestCase):
    def test_replacement_characters_ask_for_utf8_output(self):
        result = found(ran("python report.py", f"Contract {chr(0xFFFD)} one debt\n"))[0]
        self.assertEqual((result.code, result.message),
                         (Code.MOJIBAKE,
                          "The output holds 1 U+FFFD character, each where bytes were not UTF-8."),
                         "a cp1252 dash read as UTF-8 became U+FFFD")
        self.assertIn("PYTHONUTF8=1", result.fix.text, "the program's output must be UTF-8")

    def test_utf8_read_in_a_code_page_asks_for_utf8_input(self):
        result = found(ran("python report.py", "caf" + "\u00c3\u00a9" + "\n"))[0]
        self.assertIn("such as " + "\u00c3\u00a9" + " for " + "\u00e9", result.message,
                      "the message shows the garbled text and what it meant")
        self.assertIn("encoding=\"utf-8\"", result.fix.text, "the input must be read as UTF-8")

    def test_binary_output_is_not_mojibake(self):
        self.assertEqual(codes(ran("cat Hero.uasset", "\x00\x01" + chr(0xFFFD) * 40)), [],
                         "a dump of a binary file was asked for")


class ARunAfterAFailedBuild(unittest.TestCase):
    def test_a_run_after_a_failed_build_is_stale(self):
        ctx = context()
        run(failed("cmake --build build", "Exit code 2\nsrc/a.cpp:3:5: error: x"), ctx)
        result = found(ran("ctest --output-on-failure", "100% tests passed"), ctx)[0]
        self.assertEqual((result.code, result.message),
                         (Code.STALE_BINARY, "The last build in this session, cmake --build, failed, so "
                                             "ctest ran what the build before it made."),
                         "the tests ran the programs the failed build did not replace (VFY-7)")

    def test_a_build_that_passes_clears_the_failure(self):
        ctx = context()
        run(failed("cmake --build build", "Exit code 2\nsrc/a.cpp:3:5: error: x"), ctx)
        run(ran("cmake --build build", "[100%] Built target app"), ctx)
        self.assertEqual(codes(ran("ctest", "100% tests passed"), ctx), [], "the run uses the new build")

    def test_a_build_and_a_run_in_one_command(self):
        result = found(failed("cmake --build build; ctest", "Exit code 8\nsrc/a.cpp:3:5: error: x"))[-1]
        self.assertEqual(result.code, Code.STALE_BINARY,
                         "ctest ran after the build in the same command failed")


class TheBudgetLearnsFromACutCommand(unittest.TestCase):
    def test_a_well_formed_command_past_learn_from_bytes_lowers_the_budget(self):
        for length, learned in ((5000, None), (5001, 5000)):
            with self.subTest(length=length):
                ctx = context()
                command = "echo " + "x" * (length - 5)
                results = found(failed(command, EOF), ctx)
                self.assertEqual(ctx.session.budget_override, learned,
                                 "the budget drops below a cut command's length, past 5,000 bytes only")
                self.assertEqual([result.code for result in results],
                                 [Code.TRANSPORT_BUDGET] if learned else [], "and the model hears why")

    def test_the_message_says_the_tool_cut_the_command(self):
        result = found(failed("echo " + "x" * 7995, EOF))[0]
        self.assertEqual((result.severity, result.message),
                         (Severity.WARNING, "The Bash tool on this machine cut this well-formed 8,000-byte "
                                            "command, so bash read it as ending inside a quote. io-guard now "
                                            "keeps this session's commands to 7,999 bytes."),
                         "the command was too long for this machine's shell, not badly quoted")

    def test_a_badly_quoted_command_teaches_nothing(self):
        ctx = context()
        found(failed("echo 'open " + "x" * 6000, EOF), ctx)
        self.assertIsNone(ctx.session.budget_override, "bash was right: the quote never closes")

    def test_a_lower_budget_learned_earlier_stays(self):
        ctx = context()
        ctx.session.budget_override = 6500
        found(failed("echo " + "x" * 7995, EOF), ctx)
        self.assertEqual(ctx.session.budget_override, 6500, "the budget only ever drops")

    def test_an_eof_that_is_not_the_bash_tools_own_teaches_nothing(self):
        command = "cat > f <<'EOF'\n" + "echo 'x\n" * 700 + "EOF\nbash f"
        for platform in (WINDOWS, MACOS):
            for error in ("Exit code 2\nf: line 3: unexpected EOF while looking for matching `''",
                          "Exit code 2\n/usr/bin/bash: eval: line 1: unexpected EOF while looking for "
                          "matching `''", "Exit code 2\nbash: line 1: unexpected EOF while looking for "
                          "matching `''"):
                with self.subTest(platform=platform.os, error=error.splitlines()[1][:20]):
                    ctx = context(platform=platform)
                    self.assertEqual(codes(failed(command, error), ctx), [],
                                     "a script's own syntax error says nothing about the Bash tool")
                    self.assertIsNone(ctx.session.budget_override, "and the budget stays")

    def test_on_macos_the_budget_drops_after_the_second_cut(self):
        ctx = context(platform=MACOS)
        first = found(failed("echo " + "x" * 7995, EOF), ctx)
        self.assertIsNone(ctx.session.budget_override,
                          "no cut is known on macOS, so one failure is not enough")
        self.assertEqual((first[0].code, first[0].severity, first[0].message),
                         (Code.TRANSPORT_BUDGET, Severity.WARNING,
                          "Bash read this well-formed 8,000-byte command as ending inside a quote. No cut is "
                          "known on macOS, so io-guard lowers this session's budget only after a second "
                          "one."),
                         "the model hears what one more such failure does")
        found(failed("echo " + "x" * 6995, EOF), ctx)
        self.assertEqual(ctx.session.budget_override, 6999, "the second cut lowers it below the shorter one")


if __name__ == "__main__":
    unittest.main()
