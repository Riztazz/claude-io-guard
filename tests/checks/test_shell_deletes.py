"""shell.deletes refuses a shell delete outside the repository, the scratchpad and the temp folder, a
recursive delete of one of them or of the repository's .git, and a delete whose target has no path before
the command runs. The first row is the command that emptied C: on 2026-10-13. Each refused row names the
reason its message gives."""
import sys
import tempfile
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import Registry, default_registry
from ioguard.checks.shell_deletes import ShellDeletes
from ioguard.lib.config import Config, defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeFs, FakeGit
from ioguard.lib.platform import Platform, detect
from ioguard.lib.ports import LiveFs
from ioguard.lib.results import Code
from tests.support import events

ROOT = Path("C:/project")
SCRATCH = Path("C:/scratch")
TEMP = Path("C:/Users/u/AppData/Local/Temp")
WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)
ENV = {"TEMP": TEMP.as_posix(), "HOME": "C:/Users/u", "USERPROFILE": "C:/Users/u"}
NPM_CACHE = "C\uf03a"          # npm's folder for C:, as Git Bash writes it on disk
FILES = {ROOT / NPM_CACHE / "_cacache" / "index": b"", ROOT / "build" / "out.o": b"",
         ROOT / "node_modules" / "a" / "index.js": b"", ROOT / "src" / "a.py": b"",
         ROOT / ".git" / "HEAD": b"", ROOT / ".git" / "objects" / "ab": b"", SCRATCH / "out" / "log.txt": b"",
         TEMP / "x" / "y": b""}
LINKS = {ROOT / "link": Path("C:/elsewhere")}
OUTSIDE = "outside the allowed folders"
LATER = "has a value only when the command runs"
ITSELF = "an allowed folder itself"
GIT = "the repository's .git folder or inside it"
DEEP = "nests deeper than io-guard reads"


def windows_context(**overrides) -> Context:
    built = dict(platform=WINDOWS, git=FakeGit(root=ROOT), fs=FakeFs(FILES, links=LINKS), env=ENV)
    return Context.fake(**{**built, **overrides})


def message(command: str, tool: str = "Bash", cwd: Path = ROOT, ctx: Context | None = None,
            scratchpad: Path = SCRATCH) -> str | None:
    """The refusal's message, or None when the command passes."""
    ctx = ctx or windows_context()
    raw = events.bash(command, cwd) if tool == "Bash" else events.powershell(command, cwd)
    raw["scratchpad_dir"] = str(scratchpad)
    registry = Registry()
    registry.register(ShellDeletes)
    event = Event.from_hook_json(raw, Surface.MCP_HOOK, ctx.platform)
    outcome = Pipeline(registry).run(event, ctx)
    if outcome.verdict is not Verdict.DENY:
        return None
    result = outcome.decisions[0].results[0]
    assert result.code is Code.SHELL_DELETE, f"the refusal is SHELL_DELETE, not {result.code}"
    return result.message


class Table(unittest.TestCase):
    def assert_refused_for(self, rows: dict[str, str], tool: str = "Bash", **kwargs) -> None:
        """Each command is refused, and its message gives the reason the row names."""
        for command, reason in rows.items():
            with self.subTest(command=command):
                refused = message(command, tool, **kwargs)
                self.assertIsNotNone(refused, f"{command} is refused")
                self.assertIn(reason, refused, f"{command} is refused because {reason}")

    def assert_passed(self, commands: tuple[str, ...], tool: str = "Bash", **kwargs) -> None:
        for command in commands:
            with self.subTest(command=command):
                self.assertIsNone(message(command, tool, **kwargs), f"{command} deletes inside the folders")


class TheCommandThatEmptiedTheDriveIsRefused(unittest.TestCase):
    def test_rm_rf_c_question_mark_matches_the_npm_folder_as_the_drive(self):
        refused = message("rm -rf -- C?/")
        self.assertIsNotNone(refused, "C?/ matches C + U+F03A, which Git Bash passes on as C:/")
        self.assertIn("C:/", refused, "the message names the drive the glob turned into")

    def test_the_same_glob_quoted_names_only_a_folder_in_the_repository(self):
        self.assertIsNone(message("rm -rf -- 'C?/'"), "a quoted ? is no wildcard, so rm gets C?/ as written")


class ADeleteOutsideTheRootsIsRefused(Table):
    def test_a_bash_delete_outside_the_roots_is_refused(self):
        self.assert_refused_for({
            "rm -rf /c/Users": OUTSIDE, "rm -f C:/Windows/notes.txt": OUTSIDE, "rm -rf ../other": OUTSIDE,
            "cd .. && rm -rf other": OUTSIDE, "find / -name x -exec rm -rf {} +": "a Git Bash folder",
            "bash -c 'rm -rf /c/x'": OUTSIDE, "echo $(rm -rf /c/x)": OUTSIDE, "echo `rm -rf /c/x`": OUTSIDE,
            "sudo rm -rf /c/x": OUTSIDE, "eval rm -rf /c/x": OUTSIDE, "rm -rf link/inner": OUTSIDE,
            "rm -rf ~": OUTSIDE, "powershell -Command Remove-Item -Recurse C:/x": OUTSIDE,
            "cmd /c rd /s /q \"C:\\Windows\"": OUTSIDE, "unlink C:/x.txt": OUTSIDE,
            "git -C C:/other clean -fd": OUTSIDE, "rm /c/Users/u/x -rf": OUTSIDE})

    def test_a_powershell_delete_outside_the_roots_is_refused(self):
        self.assert_refused_for({
            "Remove-Item -Recurse -Force C:\\Users": OUTSIDE, "rm -r -fo C:/Windows": OUTSIDE,
            "[IO.Directory]::Delete('C:/x', $true)": OUTSIDE,
            "[System.IO.File]::Delete(\"C:/x.txt\")": OUTSIDE,
            "Remove-Item -Path build,C:/x": OUTSIDE, "Remove-Item -LiteralPath:C:/x": OUTSIDE,
            "cmd /c del /s /q C:\\*.tmp": OUTSIDE, "bash -c 'rm -rf /c/x'": OUTSIDE,
            "Get-ChildItem C:/ | ForEach-Object { Remove-Item -Recurse C:/x }": OUTSIDE,
            "Remove-Item -Recurse C:/x -WhatIf:$false": OUTSIDE}, "PowerShell")

    def test_the_message_names_the_real_path_behind_a_link(self):
        self.assertIn("C:/elsewhere/inner", message("rm -rf link/inner"),
                      "a link inside the repository that leads out is named by where it leads")


class EachWayTheReviewFoundAroundTheCheckIsClosed(Table):
    def test_each_bash_way_around_the_first_version_is_refused(self):
        self.assert_refused_for({
            "cmd //c \"rd /s /q C:\\Users\"": OUTSIDE,
            "echo 'rm -rf /c/Users' | bash": "reads its commands from a pipe",
            "bash <<< 'rm -rf /c/Users'": OUTSIDE,
            "bash <<'EOF'\nrm -rf /c/Users\nEOF\n": OUTSIDE,
            "rm -rf .git/*": GIT, "rm -rf .git/objects": GIT, "rm -f .git/*": GIT,
            "shopt -s dotglob && rm -rf *": GIT,
            "shopt -s nocaseglob; rm -rf c?/": OUTSIDE,
            "shopt -s extglob; rm -rf !(src)": "extglob",
            "cmd //c \"mklink /J link2 C:\\Users\" && rm -rf link2/*": "makes a link",
            "ln -s /c/Users here && rm -rf here/*": "makes a link",
            "find . -name x | xargs -I{} sh -c 'rm -rf {}'": "from its input",
            "find . -name x -exec sh -c 'rm -rf /c/x' \\;": OUTSIDE,
            "sudo -u root rm -rf /c/x": OUTSIDE, "exec -a name rm -rf /c/x": OUTSIDE,
            "command -p rm -rf /c/x": OUTSIDE, "busybox rm -rf /c/x": OUTSIDE,
            "cmd /c \"rd /s/q C:\\project\"": ITSELF,
            "eval eval eval eval eval rm -rf /c/x": DEEP,
            "echo $(echo $(echo $(echo $(echo $(rm -rf /c/x)))))": DEEP,
            "cd /c/Users && echo $(rm -rf x)": OUTSIDE,
            "rm -rf 'C:/Users\x00'": "NUL"})

    def test_each_powershell_way_around_the_first_version_is_refused(self):
        self.assert_refused_for({
            "$p = @{Path='C:\\Users\\x'; Recurse=$true}; Remove-Item @p": "splatted table",
            "cd C:\\Users; if ($true) { Remove-Item -Recurse x }": OUTSIDE,
            "Invoke-Expression 'Remove-Item -Recurse C:/x'": OUTSIDE,
            "iex $cmd": "Invoke-Expression runs a string",
            "Remove-Item Microsoft.PowerShell.Core\\FileSystem::C:\\x": "a PowerShell provider",
            "[IO.Directory]::Delete('C:/project', 1)": ITSELF,
            "'rm -rf /c/x' | bash": "reads its commands from a pipe"}, "PowerShell")


class EachWayTheSecondReviewFoundIsClosed(Table):
    def test_each_bash_way_around_the_second_version_is_refused(self):
        self.assert_refused_for({
            "cmd //c \"cd .. & rd /s /q project\"": "after a cd io-guard cannot follow",
            "cat <<EOF > n.txt\nhello\nEOF\necho 'rm -rf /c/Users' | bash": "reads its commands from a pipe",
            "cat <<EOF\n$(rm -rf /c/x)\nEOF\n": OUTSIDE,
            "echo \\\\`rm -rf /c/x`": OUTSIDE,
            "nohup sudo -u root rm -rf /c/x": OUTSIDE, "time sudo -u root rm -rf /c/x": OUTSIDE,
            "find / -name x | sudo xargs rm -rf": "from its input",
            "c='rm -rf /c/x'; eval \"$c\"": "held in a variable",
            "c='rm -rf /c/x'; bash -c \"$c\"": "held in a variable",
            "find . -name .git -exec rm -rf {} +": ITSELF, "find . -name '*' -exec rm -rf {} +": ITSELF,
            "find . -mtime +7 -exec rm -rf {} +": ITSELF,
            "echo 'rm -rf /c/x' |& bash": "reads its commands from a pipe",
            "cmd //c \"rd/s/q C:\\x\"": OUTSIDE, "cmd //c \"if exist C:\\x rd /s /q C:\\x\"": OUTSIDE,
            "x=$(ln -s /c/Users here); rm -rf here/*": "makes a link",
            "eval eval eval eval eval 'r\\m -rf /c/x'": DEEP})

    def test_each_powershell_way_around_the_second_version_is_refused(self):
        self.assert_refused_for({
            "# Remove-Item -Recurse x\ncd C:\\Users\n& { Remove-Item -Recurse x }": OUTSIDE,
            "if ($true) { cd C:\\Users }; Remove-Item -Recurse x": "after a cd io-guard cannot follow",
            "New-Item -Type Junction -Path j -Target C:\\Users; Remove-Item -Recurse j": "makes a link",
            "[IO.Directory]::CreateSymbolicLink('j', 'C:/Users'); Remove-Item -Recurse j": "makes a link"},
            "PowerShell")

    def test_what_the_second_version_refused_by_mistake_passes(self):
        self.assert_passed(("grep x <<< 'rm -rf /c/x'; bash", "echo 'shopt -s extglob'; rm -rf build"))
        self.assert_passed(("bash --version",), "PowerShell")


class WhatTheShippedCheckRefusedByMistakePasses(Table):
    def test_a_link_made_after_every_delete_passes(self):
        self.assert_passed(("rm -rf dist && ln -s build dist",))
        self.assert_passed(("Remove-Item -Recurse dist; New-Item -Type SymbolicLink -Path dist -Target b",),
                           "PowerShell")

    def test_a_link_made_before_beside_or_around_a_delete_is_refused(self):
        self.assert_refused_for({
            "ln -s /c/Users here && rm -rf here/*": "makes a link",
            "for i in 1 2; do rm -rf here/*; ln -s /c/Users here; done": "makes a link",
            "rm -rf here/* & ln -s /c/Users here": "makes a link"})

    def test_a_bash_delete_of_a_link_itself_is_judged_where_the_link_is(self):
        self.assert_passed(("rm link", "rm -rf link", "rm -f 'link'", "unlink link"))
        refused = message("rm -rf link/")
        self.assertIsNotNone(refused, "a trailing slash empties the folder the link leads to")
        self.assertIn("C:/elsewhere", refused, "and the message names that folder")

    def test_powershell_judges_a_link_by_where_it_leads(self):
        self.assert_refused_for({"Remove-Item -Recurse link": OUTSIDE}, "PowerShell")

    def test_a_working_folder_in_a_submodule_takes_the_repository_above_it(self):
        sub = ROOT / "sub"
        ctx = windows_context(git=FakeGit(root=sub, superprojects={sub: ROOT}))
        self.assert_passed(("rm -f ../src/a.py", "rm -rf ../build"), cwd=sub, ctx=ctx)
        self.assert_refused_for({"rm -rf ..": ITSELF, "rm -rf ../.git": GIT}, cwd=sub, ctx=ctx)

    def test_a_repository_that_is_not_a_submodule_is_its_own_top(self):
        sub = ROOT / "sub"
        self.assert_refused_for({"rm -f ../src/a.py": OUTSIDE}, cwd=sub,
                                ctx=windows_context(git=FakeGit(root=sub)))


class ACommandNestedPastWhatIoGuardReads(Table):
    BASH = '"${a:-' * 3000 + "x" + '}"' * 3000
    POWERSHELL = '"$(' * 3000 + "x" + ')"' * 3000

    def test_it_passes_when_it_names_no_delete(self):
        self.assert_passed((f"echo {self.BASH}",))
        self.assert_passed((f"echo {self.POWERSHELL}",), "PowerShell")

    def test_it_is_refused_as_unread_when_it_names_a_delete(self):
        self.assert_refused_for({f"rm -f x; echo {self.BASH}": DEEP})
        self.assert_refused_for({f"Remove-Item x; echo {self.POWERSHELL}": DEEP}, "PowerShell")


class ARecursiveDeleteOfARootOrOfGitIsRefused(Table):
    def test_each_fenced_target(self):
        self.assert_refused_for({
            "rm -rf .": ITSELF, "rm -rf /c/project": ITSELF, "rm -rf .git": GIT, "rm -rf /tmp": ITSELF,
            "rm -rf C:/scratch": ITSELF, "git rm -r .": ITSELF, "rm -rf C:/": OUTSIDE,
            "find . -exec rm -rf {} +": ITSELF, "find . -type d -exec rm -rf {} +": ITSELF})

    def test_one_named_file_inside_the_git_folder_passes(self):
        self.assertIsNone(message("rm -f .git/index.lock"),
                          "a single named file inside .git is a normal delete")

    def test_a_folder_inside_one_root_that_holds_another_is_fenced(self):
        ctx = windows_context(env={**ENV, "TEMP": "C:/project/cache/tmp"})
        self.assertIn("it holds an allowed folder", message("rm -rf cache", ctx=ctx),
                      "cache is inside the repository and holds the temp folder, so a recursive delete of it "
                      "is fenced")
        self.assertIsNone(message("rm -f cache/note.txt", ctx=ctx),
                          "one file in that folder is a normal delete")


class ATargetWithNoPathBeforeTheRunIsRefused(Table):
    def test_a_bash_target_known_only_at_run_time_is_refused(self):
        self.assert_refused_for({
            'rm -rf "$DIR"': LATER, "rm -rf $(pwd)/build": LATER, "ls | xargs rm -rf": "from its input",
            "rm -rf build{,2}": "a brace list", "rm -rf /usr/local": "a Git Bash folder",
            "rm -rf ~other/x": "another user's home folder", "for f in *; do rm -rf \"$f\"; done": LATER,
            "rm -rf 'unclosed": "quotes do not close"})

    def test_a_powershell_target_known_only_at_run_time_is_refused(self):
        self.assert_refused_for({
            "Remove-Item $env:TEMP\\x -Recurse": LATER,
            "Get-ChildItem build | Remove-Item": "from the pipeline",
            "Remove-Item HKCU:\\Software\\x -Recurse": "a PowerShell provider",
            "Remove-Item \"C:/x$name\"": LATER,
            "cmd /c del %TEMP%\\x": LATER}, "PowerShell")


class ADeleteInsideTheRootsPasses(Table):
    def test_a_bash_delete_inside_the_roots_passes(self):
        self.assert_passed((
            "rm -rf build", "rm -f src/a.py", "rm -rf node_modules/*", "rm -rf /tmp/x",
            "rm -rf C:/scratch/out",
            "git clean -fd build", "git clean -n", "git rm --cached -r .", "echo rm -rf /",
            "rm -rf build/ src/a.py", "rmdir build", "rm -rf -- -weird", "cd build && rm -f out.o",
            "find build -name '*.o' -exec rm {} +", "find . -name '*.pyc' -exec rm -f {} +",
            "find . -type d -name __pycache__ -exec rm -rf {} +", "git clean -fd", "git clean -fdx",
            "cd /tmp && rm -rf x", "rm -rf \"\"", "command -v rm", "bash script.sh",
            "cat <<'EOF' > notes.txt\nrm -rf /c/x\nEOF\n"))

    def test_a_powershell_delete_inside_the_roots_passes(self):
        self.assert_passed((
            "Remove-Item -Recurse -Force build", "Remove-Item 'src/a.py'",
            "Remove-Item -LiteralPath 'build[1]'",
            "Remove-Item C:/scratch/out -Recurse", "Remove-Item -Recurse build -ErrorAction SilentlyContinue",
            "Remove-Item node_modules/* -Recurse", "cmd /c rd /s /q build",
            "Remove-Item build -ProgressAction SilentlyContinue -Recurse",
            "Remove-Item C:/project -Recurse:$false", "Remove-Item -Recurse C:/x -WhatIf"), "PowerShell")

    def test_a_folder_in_the_roots_setting_is_allowed(self):
        values = {**defaults(default_registry().keys()).values, "checks.shell.deletes.roots": ["C:/data"]}
        ctx = windows_context(config=Config(values))
        self.assertIsNone(message("rm -rf C:/data/old", ctx=ctx),
                          "a configured root is allowed like the others")
        self.assertIsNotNone(message("rm -rf C:/data/old"), "without the setting the same folder is outside")

    def test_a_root_setting_starting_with_a_tilde_is_under_the_home_folder(self):
        values = {**defaults(default_registry().keys()).values,
                  "checks.shell.deletes.roots": ["~/.claude/projects"]}
        ctx = windows_context(config=Config(values))
        self.assertIsNone(message("rm -f /c/Users/u/.claude/projects/p/memory/old.md", ctx=ctx),
                          "~ in a root is the home folder, so a memory file there may be deleted")


class OnMacOsTheTmpFolderIsATempRoot(Table):
    def test_tmp_and_tmpdir_both_pass(self):
        root = Path("/Users/u/project")
        ctx = Context.fake(platform=MACOS, git=FakeGit(root=root), fs=FakeFs({root / "a": b""}),
                           env={"TMPDIR": "/var/folders/x/T", "HOME": "/Users/u"})
        self.assert_passed(("rm -rf /tmp/x", "rm -rf /var/folders/x/T/y"), cwd=root, ctx=ctx,
                           scratchpad=Path("/Users/u/scratch"))
        self.assert_refused_for({"rm -rf /Users/u/Documents": OUTSIDE}, cwd=root, ctx=ctx,
                                scratchpad=Path("/Users/u/scratch"))


@unittest.skipUnless(sys.platform == "win32", "Git Bash's private-use names exist only on Windows")
class OnARealDiskTheNpmFolderIsSeenAsTheDrive(unittest.TestCase):
    def test_the_glob_over_a_real_folder_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / NPM_CACHE).mkdir()
            ctx = Context.fake(platform=detect(), git=FakeGit(root=root), fs=LiveFs(),
                               env={"TEMP": (root / "temp").as_posix()})
            refused = message("rm -rf -- C?/", cwd=root, ctx=ctx, scratchpad=root / "scratch")
            self.assertIsNotNone(refused, "LiveFs lists the folder, and the check maps its name to C:")
            self.assertIn("C:/", refused, "the message names the drive")


if __name__ == "__main__":
    unittest.main()
