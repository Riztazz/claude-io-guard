"""shell.writes refuses a shell write to a file git tracks, passes every other write, and ports each rule of
the kit's shell-write-guard.py."""
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry
from ioguard.checks.shell_writes import ShellWrites
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeGit
from ioguard.lib.git import GitError
from ioguard.lib.platform import Platform
from ioguard.lib.results import Code, Severity
from tests.support import events

ROOT = Path("C:/project")
SCRATCH = Path("C:/scratch")
WINDOWS = Platform("win32", True)
TRACKED = frozenset({ROOT / "src" / "a.py", ROOT / "README.md"})


class CountingGit(FakeGit):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.asked: list[Path] = []

    def is_tracked(self, path: Path) -> bool:
        self.asked.append(path)
        return super().is_tracked(path)


def run(command: str, tool: str = "Bash", git: FakeGit | None = None, files: dict | None = None):
    git = git or CountingGit(root=ROOT, tracked=TRACKED)
    ctx = Context.fake(files=files or {}, platform=WINDOWS, git=git)
    raw = events.bash(command, ROOT) if tool == "Bash" else events.powershell(command, ROOT)
    raw["scratchpad_dir"] = str(SCRATCH)
    registry = Registry()
    registry.register(ShellWrites)
    event = Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS)
    return Pipeline(registry).run(event, ctx), ctx


def refused(command: str, tool: str = "Bash", **kwargs) -> bool:
    outcome, _ = run(command, tool, **kwargs)
    return outcome.verdict is Verdict.DENY and outcome.decisions[0].results[0].code is Code.SHELL_WRITE


class EveryRuleOfTheKitsGuardIsPorted(unittest.TestCase):
    def test_each_rule_refuses_a_write_to_a_tracked_file(self):
        rules = {
            "an interpreter reading a heredoc that writes a file":
                "python - <<'PY'\nopen('src/a.py', 'w').write('x')\nPY\n",
            "python -c with code that writes a file": "python -c \"open('src/a.py', 'w').write('x')\"",
            "a heredoc redirected into a file": "cat > src/a.py <<'EOF'\nx = 1\nEOF\n",
            "an in-place edit by sed or perl": "sed -i 's/a/b/' src/a.py",
            "echo or printf redirected into a source, config or JSON file": "printf 'x' >> README.md",
        }
        for rule, command in rules.items():
            with self.subTest(rule=rule):
                self.assertTrue(refused(command), f"{rule} is still refused for a tracked file")

    def test_a_powershell_here_string_written_to_a_tracked_file(self):
        self.assertTrue(refused("@'\nx = 1\n'@ | Set-Content src/a.py", "PowerShell"),
                        "the kit's here-string rule, now on the tracked target")


class EveryWriteFormIsFound(unittest.TestCase):
    def test_bash_forms(self):
        for command in ("echo x | tee -a src/a.py", "cp /tmp/a.py src/a.py", "mv new.md README.md",
                        "perl -pi -e 's/a/b/' src/a.py", "python x.py &> README.md",
                        "sed -e 's/a/b/' -i src/a.py", "echo x > /c/project/README.md"):
            with self.subTest(command=command):
                self.assertTrue(refused(command), "the write is found and its target is tracked")

    def test_powershell_forms(self):
        for command in ("'x' | Out-File -FilePath src/a.py", "Add-Content -Path README.md -Value x",
                        "[IO.File]::WriteAllText('C:/project/README.md', 'x')",
                        "Copy-Item new.md -Destination README.md", "Get-Date > README.md"):
            with self.subTest(command=command):
                self.assertTrue(refused(command, "PowerShell"),
                                "the write is found and its target is tracked")

    def test_a_body_task_11_moved_is_read_from_its_file(self):
        body = SCRATCH / "io-guard" / "body-0123456789abcdef.txt"
        command = f'python - < "{body.as_posix()}"'
        self.assertTrue(refused(command, files={body: b"open('src/a.py', 'w').write('x')\n"}),
                        "the moved body still writes a tracked file")


class EverythingElsePasses(unittest.TestCase):
    def test_writes_io_guard_cannot_stop_pass(self):
        for command in ("echo x > notes.txt", "echo x > /dev/null", "echo x > $S/a.py", "ls 2>&1 | head",
                        f"echo x > {SCRATCH.as_posix()}/a.py", "echo x > ~/a.txt", "cat src/a.py"):
            with self.subTest(command=command):
                outcome, _ = run(command)
                self.assertEqual(outcome.verdict, Verdict.OBSERVE,
                                 "an untracked, device, variable, scratch or read-only target passes")

    def test_the_command_that_broke_the_kits_guard_passes(self):
        outcome, _ = run("git commit -m @'\nfix: a thing\n'@ 2>&1 | Select-Object -Last 6", "PowerShell")
        self.assertEqual(outcome.verdict, Verdict.OBSERVE,
                         "SHW-8: 2>&1 duplicates a stream and writes no file")

    def test_a_write_named_inside_a_bodys_text_is_not_a_write(self):
        command = ("python - <<'PY'\ncases = [\"cat > src/a.py <<'EOF'\", \"sed -i x README.md\"]\n"
                   "print(cases)\nPY\n")
        outcome, _ = run(command)
        self.assertEqual(outcome.verdict, Verdict.OBSERVE,
                         "GRD-1: a command's words inside a Python string are data, not a write")

    def test_a_write_named_inside_a_quoted_argument_is_not_a_write(self):
        outcome, _ = run("grep -n 'sed -i s/a/b/ README.md\\|cat > src/a.py' notes.txt")
        self.assertEqual(outcome.verdict, Verdict.OBSERVE,
                         "GRD-1: a grep pattern that quotes a write is one argument to grep, not a write")

    def test_outside_any_repository_passes(self):
        self.assertFalse(refused("echo x > README.md", git=CountingGit(root=None, tracked=TRACKED)),
                         "with no repository there is nothing git tracks")

    def test_a_git_that_cannot_answer_lets_the_write_pass(self):
        broken = CountingGit(root=ROOT, tracked=TRACKED)
        broken.root = lambda path: (_ for _ in ()).throw(GitError("git timed out"))
        self.assertFalse(refused("echo x > README.md", git=broken), "unknown is not a refusal")


class ACdMovesWhereTargetsResolve(unittest.TestCase):
    def test_a_cd_into_the_repository_is_followed(self):
        self.assertTrue(refused("cd src && sed -i 's/a/b/' a.py"), "a.py after cd src is src/a.py")
        self.assertTrue(refused("Set-Location src; 'x' | Out-File a.py", "PowerShell"),
                        "Set-Location moves PowerShell's targets the same way")

    def test_a_cd_elsewhere_moves_the_target_out(self):
        self.assertFalse(refused(f"cd {SCRATCH.as_posix()} && echo x > README.md"),
                         "README.md after cd to the scratchpad is the scratchpad's")

    def test_after_a_cd_io_guard_cannot_follow_a_relative_target_passes(self):
        outcome, _ = run('cd "$S" && cat > try.py <<\'EOF\'\nprint(1)\nEOF\n')
        self.assertEqual(outcome.verdict, Verdict.OBSERVE,
                         "a cd to a variable leaves the target unknown, so neither a refusal nor a warning")


class TheRefusalAndTheWarning(unittest.TestCase):
    def test_the_refusal_names_the_target_the_route_and_the_fix(self):
        outcome, _ = run("sed -i 's/a/b/' src/a.py")
        text = outcome.decisions[0].results[0].render()
        for part in ("SHELL_WRITE:", "C:/project/src/a.py", "sed -i", "Edit tool"):
            with self.subTest(part=part):
                self.assertIn(part, text, "the model reads what, how and what to do instead")

    def test_a_script_created_in_the_repository_is_a_warning(self):
        outcome, _ = run("cat > tools/try.py <<'EOF'\nprint(1)\nEOF\n")
        result = outcome.decisions[0].results[0]
        self.assertEqual((outcome.verdict, result.severity), (Verdict.ALLOW, Severity.WARNING),
                         "GIT-1: a scratch script in the repository runs, with a warning")
        self.assertIn(SCRATCH.as_posix(), result.render(), "the warning points at the scratchpad")

    def test_git_is_asked_once_per_path_in_a_session(self):
        git = CountingGit(root=ROOT, tracked=TRACKED)
        ctx = Context.fake(platform=WINDOWS, git=git)
        registry = Registry()
        registry.register(ShellWrites)
        for _ in range(3):
            event = Event.from_hook_json(events.bash("echo x > notes.txt", ROOT), Surface.MCP_HOOK, WINDOWS)
            Pipeline(registry).run(event, ctx)
        self.assertEqual(len(git.asked), 1, "the answer is cached for the session")


if __name__ == "__main__":
    unittest.main()
