"""shell.lint refuses a command whose quoting, escaping or dialect would change what runs, fixes a Windows
path whose last backslash escapes its quote, and passes the commands that mean what they say."""
import unittest
from dataclasses import replace
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.checks.session_probe import WINDOWS_CUT
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context, Probe
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, Severity
from tests.support import events

CWD = Path("C:/project")
SCRATCH = Path("C:/scratch")
WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)
REGISTRY = default_registry()


def context(files: dict | None = None, **config) -> Context:
    probe = replace(Probe.unprobed(WINDOWS), transport_budget=WINDOWS_CUT, halving=True)
    values = {**defaults(REGISTRY.keys()).values, **{f"checks.shell.lint.{key}": value
                                                      for key, value in config.items()}}
    return Context.fake(files=files or {}, config=Config(values), platform=WINDOWS, probe=probe)


def run(command: str, tool: str = "Bash", ctx: Context | None = None, scratchpad: Path | None = SCRATCH):
    raw = events.bash(command, CWD) if tool == "Bash" else events.powershell(command, CWD)
    raw["scratchpad_dir"] = "" if scratchpad is None else str(scratchpad)
    event = Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS)
    return Pipeline(REGISTRY).run(event, ctx or context())


def lint(outcome):
    return next(decision for decision in outcome.decisions if decision.check_id == "shell.lint")


def codes(command: str, tool: str = "Bash", **kwargs) -> tuple[Verdict, tuple[Code, ...]]:
    decision = lint(run(command, tool, **kwargs))
    return decision.verdict, tuple(result.code for result in decision.results)


class BackticksInsideDoubleQuotes(unittest.TestCase):
    def test_a_backtick_inside_double_quotes_is_refused(self):
        for command in ('git commit -m "fix `parse` for empty input"', "grep -n \"^### \\|^```\" README.md"):
            with self.subTest(command=command):
                self.assertEqual(codes(command), (Verdict.DENY, (Code.BACKTICK_IN_DOUBLE_QUOTES,)),
                                 "bash would run the text between backticks, or wait for the closing one")

    def test_an_escaped_or_single_quoted_backtick_passes(self):
        for command in ('echo "a \\`b\\` c"', "echo 'a `b` c'", "grep -c '^```' README.md", "echo `date`"):
            with self.subTest(command=command):
                self.assertEqual(codes(command), (Verdict.OBSERVE, ()), "the backtick means what it says")


class AWindowsPathWhoseBackslashEscapesItsQuote(unittest.TestCase):
    def test_the_path_is_rewritten_with_forward_slashes(self):
        outcome = run(r'ls "C:\Users\me\dir\" 2>&1')
        self.assertEqual((outcome.tool_input["command"], outcome.rewrites[0].code),
                         ('ls "C:/Users/me/dir/" 2>&1', Code.TRAILING_BACKSLASH_QUOTE),
                         "the backslash no longer escapes the quote, and the path names the same folder")

    def test_the_rewrite_is_a_fixed_point(self):
        again = run(run(r'ls "C:\a b\c\" && cat "C:\d\e.md"').tool_input["command"])
        self.assertEqual((again.verdict, again.rewrites), (Verdict.OBSERVE, ()),
                         "the rewritten command needs no second rewrite")

    def test_a_command_bash_reads_to_the_end_is_left_alone(self):
        self.assertEqual(codes(r'ls "C:\dir\\"'), (Verdict.OBSERVE, ()),
                         "an escaped backslash before the quote closes the string as written")


class PowerShellSentToBash(unittest.TestCase):
    def test_the_call_operator_is_refused(self):
        for command in ('& "C:/Program Files/Tool/tool.exe" --build', 'cd x && & "C:/t.exe"',
                        "echo ok\n& true"):
            with self.subTest(command=command):
                self.assertEqual(codes(command), (Verdict.DENY, (Code.DIALECT_MISMATCH,)),
                                 "bash reads an & that starts a command as a syntax error")

    def test_the_ampersands_bash_uses_pass(self):
        for command in ("a && b", "sleep 1 &", "ls 2>&1 | head", "make &> log", "a |& b", "a & b"):
            with self.subTest(command=command):
                self.assertEqual(codes(command), (Verdict.OBSERVE, ()), "each of these is bash")

    def test_a_powershell_variable_bash_expands_is_refused(self):
        for command in ('powershell -Command "Get-Process | ForEach-Object { $_.Id }"',
                        'cat "$env:USERPROFILE/notes.txt"', "Get-ChildItem .", "$m = @'\nline\n'@\necho $m"):
            with self.subTest(command=command):
                verdict, found = codes(command)
                self.assertEqual((verdict, found[0]), (Verdict.DENY, Code.DIALECT_MISMATCH),
                                 "PowerShell syntax does something else in bash, and the refusal says so")

    def test_powershell_text_bash_leaves_alone_passes(self):
        for command in ("powershell -Command 'Get-Process | ForEach-Object { $_.Id }'",
                        'powershell -Command "Get-Process | ForEach-Object { \\$_.Id }"', "echo $_"):
            with self.subTest(command=command):
                self.assertEqual(codes(command), (Verdict.OBSERVE, ()),
                                 "single quotes and an escaped $ reach PowerShell, and $_ alone is bash's")


class PythonBodies(unittest.TestCase):
    def test_a_body_that_does_not_compile_is_refused(self):
        for command in ("python - <<'PY'\nprint('a'\nPY\n", 'python -c "print(1"',
                        "python - <<'PY'\np = \"C:\\Users\\me\"\nPY\n"):
            with self.subTest(command=command):
                decision = lint(run(command))
                self.assertEqual((decision.verdict, decision.results[0].code),
                                 (Verdict.DENY, Code.INLINE_SCRIPT_INVALID),
                                 "Python would stop before it ran")
                self.assertIn("line", decision.results[0].message, "the refusal names the line")

    def test_a_body_that_compiles_with_a_warning_runs_with_it(self):
        decision = lint(run("python - <<'PY'\nimport re\nprint(re.findall(\"\\d\", \"a1\"))\nPY\n"))
        self.assertEqual((decision.verdict, decision.results[0].code, decision.results[0].severity),
                         (Verdict.ALLOW, Code.INLINE_SCRIPT_INVALID, Severity.WARNING),
                         "an invalid escape runs, and the model reads the warning")

    def test_a_body_python_does_not_run_as_its_program_is_not_compiled(self):
        for command in ("cat > a.h <<'EOF'\nint x = 01;\nEOF\n", "python tool.py <<'EOF'\nnot python\nEOF\n",
                        "python - <<EOF\nprint('$HOME'\nEOF\n"):
            with self.subTest(command=command):
                self.assertEqual(codes(command), (Verdict.OBSERVE, ()),
                                 "data, a script's stdin, or a body bash expands is not compiled")

    def test_a_moved_body_is_compiled_from_its_file(self):
        body = SCRATCH / "io-guard" / "body-0123456789abcdef.txt"
        ctx = context(files={body: b"print('a'\n"})
        self.assertEqual(codes(f'python - < "{body.as_posix()}"', ctx=ctx),
                         (Verdict.DENY, (Code.INLINE_SCRIPT_INVALID,)),
                         "the file holds the body Python reads")

    def test_a_body_the_bash_tool_halves_is_not_compiled(self):
        command = "python - <<'PY'\nprint('a\\\\\\\\b'\nPY\n"
        self.assertEqual(codes(command, scratchpad=None), (Verdict.OBSERVE, ()),
                         "with nowhere to move it, Python reads another text than the one written")


class APipeHidesABuildsExitCode(unittest.TestCase):
    def test_a_build_piped_into_a_filter_gets_a_warning(self):
        decision = lint(run("make all 2>&1 | tail -20"))
        self.assertEqual((decision.verdict, decision.results[0].code), (Verdict.ALLOW, Code.PIPE_HIDES_EXIT),
                         "the exit code shown is tail's")

    def test_a_pipe_that_hides_nothing_passes(self):
        for command in ("set -o pipefail; make | tail", "make > log", "grep x a | head", "make || true"):
            with self.subTest(command=command):
                self.assertEqual(codes(command), (Verdict.OBSERVE, ()), "no build's exit code is lost")

    def test_a_projects_own_build_command_counts(self):
        ctx = context(build_commands=["build.bat"])
        self.assertEqual(codes('"C:/Engine/Build.bat" Game | tail -5', ctx=ctx),
                         (Verdict.ALLOW, (Code.PIPE_HIDES_EXIT,)), "the setting names the project's build")


class BashSentToPowerShell(unittest.TestCase):
    def test_bash_syntax_is_refused(self):
        for command in ("export PATH=x", "python - <<'PY'\nprint(1)\nPY", "Get-Date > /dev/null"):
            with self.subTest(command=command):
                self.assertEqual(codes(command, "PowerShell"), (Verdict.DENY, (Code.DIALECT_MISMATCH,)),
                                 "PowerShell fails on bash syntax")

    def test_tail_is_a_warning(self):
        self.assertEqual(codes("tail -5 build.log", "PowerShell"), (Verdict.ALLOW, (Code.DIALECT_MISMATCH,)),
                         "tail runs only when a program by that name is on the PATH")

    def test_on_macos_dev_null_and_tail_are_real(self):
        ctx = replace(context(), platform=MACOS, probe=Probe.unprobed(MACOS))
        for command in ("Get-Date > /dev/null", "tail -5 build.log"):
            with self.subTest(command=command):
                raw = events.powershell(command, Path("/project"))
                event = Event.from_hook_json(raw, Surface.MCP_HOOK, MACOS)
                decision = lint(Pipeline(REGISTRY).run(event, ctx))
                self.assertEqual(decision.verdict, Verdict.OBSERVE, "macOS has /dev/null, tail and head")


class PowerShellCallsThatAlwaysFail(unittest.TestCase):
    def test_each_is_refused(self):
        for command in ("Select-String -Pattern x -Path . -Recurse", "$pid = 5",
                        "foreach ($home in 1..2) { }", "if ($x) { $Error = 1 }"):
            with self.subTest(command=command):
                self.assertEqual(codes(command, "PowerShell"), (Verdict.DENY, (Code.POWERSHELL_TRAP,)),
                                 "PowerShell refuses these before they do anything")

    def test_the_forms_that_work_pass(self):
        for command in ("Select-String -Pattern x -Path (Get-ChildItem -Recurse -File)", "$null = Get-Date",
                        '"$pid = 5"', "$errors = 1", "# $pid = 5"):
            with self.subTest(command=command):
                self.assertEqual(codes(command, "PowerShell"), (Verdict.OBSERVE, ()), "each of these runs")


if __name__ == "__main__":
    unittest.main()
