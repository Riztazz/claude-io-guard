"""win.paths keeps Git Bash from turning slash arguments into paths and a redirect to nul into a file, on
Windows only."""
import unittest
from pathlib import Path

from ioguard.checks.pipeline import Pipeline
from ioguard.checks.registry import default_registry
from ioguard.lib.config import defaults
from ioguard.lib.context import Context
from ioguard.lib.decisions import Verdict
from ioguard.lib.events import Event, Surface
from ioguard.lib.platform import Platform
from ioguard.lib.probing import Probe
from ioguard.lib.results import Code
from tests.support import events

WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)
REGISTRY = default_registry()


def run(command: str, platform: Platform = WINDOWS, **config):
    values = {**defaults(REGISTRY.keys()).values, **{f"checks.win.paths.{key}": value
                                                      for key, value in config.items()}}
    ctx = Context.fake(config=type(defaults())(values), platform=platform, probe=Probe.unprobed(platform))
    cwd = Path("C:/project") if platform.windows else Path("/project")
    event = Event.from_hook_json(events.bash(command, cwd), Surface.MCP_HOOK, platform)
    return Pipeline(REGISTRY).run(event, ctx)


class SlashArgumentsKeepTheirSlash(unittest.TestCase):
    def test_a_name_passed_to_a_windows_program_is_excluded(self):
        outcome = run("python tool.py /Game/Maps/L_Lab --map=/Game/X && taskkill /PID 12 /F")
        self.assertEqual((outcome.rewrites[0].code, outcome.tool_input["command"]),
                         (Code.MSYS_PATH, "export MSYS2_ARG_CONV_EXCL='/Game/;--map=/Game/;/PID;/F'; python "
                                          "tool.py /Game/Maps/L_Lab --map=/Game/X && taskkill /PID 12 /F"),
                         "each argument Git Bash would turn into a path is named, once, before the command")

    def test_paths_meant_for_the_rewrite_and_msys_programs_are_left_alone(self):
        for command in ("python /c/Users/me/x.py /tmp/out", "grep -rn /Game/X Source", "echo /Game/X",
                        "export MSYS2_ARG_CONV_EXCL='/Game/'; python tool.py /Game/X",
                        "MSYS_NO_PATHCONV=1 python tool.py /Game/X"):
            with self.subTest(command=command):
                self.assertEqual(run(command).verdict, Verdict.OBSERVE,
                                 "a drive or /tmp path converts as meant, and grep and echo never convert")

    def test_the_exported_exclusion_is_a_fixed_point(self):
        again = run(run("python tool.py /Game/X").tool_input["command"])
        self.assertEqual((again.verdict, again.rewrites), (Verdict.OBSERVE, ()),
                         "one export is enough")

    def test_a_project_prefix_is_always_kept(self):
        outcome = run("python tool.py /tmp/Game/X", prefixes=["/tmp/Game/"])
        self.assertIn("MSYS2_ARG_CONV_EXCL='/tmp/Game/'", outcome.tool_input["command"],
                      "a prefix the project names is kept even under a POSIX root")


class CmdAndNul(unittest.TestCase):
    def test_cmd_slash_c_is_doubled(self):
        outcome = run('cmd /c "dir /b" && cmd.exe /k ver')
        self.assertEqual(outcome.tool_input["command"], 'cmd //c "dir /b" && cmd.exe //k ver',
                         "Git Bash turns //c into /c for cmd, and a lone /c into C:/")

    def test_cmd_slash_c_stays_when_the_command_turns_conversion_off(self):
        cases = {"MSYS_NO_PATHCONV=1 cmd /c dir": "MSYS_NO_PATHCONV=1 cmd /c dir",
                 "MSYS2_ARG_CONV_EXCL='*' cmd /c dir": "MSYS2_ARG_CONV_EXCL='*' cmd /c dir",
                 "MSYS2_ARG_CONV_EXCL=/ cmd /k ver": "MSYS2_ARG_CONV_EXCL=/ cmd /k ver",
                 "MSYS2_ARG_CONV_EXCL=/Game cmd /c dir": "MSYS2_ARG_CONV_EXCL=/Game cmd //c dir"}
        self.assertEqual({command: run(command).tool_input["command"] for command in cases}, cases,
                         "with conversion off for the switch, Git Bash hands //c to cmd as written, and cmd "
                         "then runs nothing")

    def test_the_note_names_the_switch_it_doubled(self):
        note = run("cmd /k ver").rewrites[0].note
        self.assertIn("io-guard wrote cmd //k, because Git Bash turns a lone /k into K:/", note,
                      "the note names /k, not /c")

    def test_a_redirect_to_nul_goes_to_dev_null(self):
        outcome = run("ls missing 2>nul; make >NUL 2>&1; echo 'x > nul'")
        self.assertEqual((outcome.rewrites[0].code, outcome.tool_input["command"]),
                         (Code.RESERVED_NAME, "ls missing 2>/dev/null; make >/dev/null 2>&1; echo 'x > nul'"),
                         "a redirect to nul would make a real file named nul, and quoted text stays")


class OnlyOnWindows(unittest.TestCase):
    def test_on_macos_nothing_changes(self):
        outcome = run("python tool.py /Game/X 2>nul && cmd /c ver", MACOS)
        self.assertEqual((outcome.verdict, outcome.rewrites), (Verdict.OBSERVE, ()),
                         "macOS has no Git Bash path rewrite and no nul device name")


if __name__ == "__main__":
    unittest.main()
