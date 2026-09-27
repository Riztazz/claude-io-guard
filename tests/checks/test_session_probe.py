"""The session probe writes probe.json and the shell defaults at SessionStart, and only the user sets them."""
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

from ioguard.checks import session_probe
from ioguard.checks.registry import Registry
from ioguard.checks.session_probe import SessionProbe
from ioguard.lib.config import Config, Scope, all_keys, defaults, validate
from ioguard.lib.context import Context, Probe, ToolVersion
from ioguard.lib.events import Event, Surface
from ioguard.lib.fakes import FakeGit
from ioguard.lib.git import GitError, GitStatus, StatusEntry
from ioguard.lib.platform import Platform
from tests.support import events

ROOT = Path("C:/project")
DATA = ROOT / "data"
ENV_FILE = ROOT / "session-env" / "sessionstart-hook-0.sh"
WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)
KEYS = {"session.probe": SessionProbe.meta.config}


def version_of(path, pattern, previous=None, **kwargs):
    return ToolVersion(path, "1.2.3", "10:10")


def context(platform: Platform = WINDOWS, env: dict | None = None, **overrides) -> Context:
    base_env = {"CLAUDE_ENV_FILE": str(ENV_FILE), "AI_AGENT": "claude-code_2-1-281_agent", "PATH": ""}
    return Context.fake(config=defaults(KEYS), platform=platform, probe=Probe.unprobed(platform),
                        env={**base_env, **(env or {})}, data_dir=DATA, **overrides)


def probed(ctx: Context) -> tuple[dict, bytes]:
    """Run the probe with every tool found at a made-up path, and return probe.json and the env file."""
    event = Event.from_hook_json(events.session_start(ROOT), Surface.COMMAND_HOOK, ctx.platform)
    registry = Registry()
    registry.register(SessionProbe)
    check = registry.instantiate(ctx.config)[0]
    with mock.patch.object(session_probe.probing, "find", lambda name, env, skip=(): f"/tools/{name}"), \
            mock.patch.object(session_probe.probing, "tool_version", version_of):
        decision = check.run(event, ctx)
    probe = json.loads(ctx.fs.files[DATA / "probe.json"]) if DATA / "probe.json" in ctx.fs.files else {}
    return probe | {"decision": decision}, ctx.fs.files.get(ENV_FILE, b"")


class TheProbeIsSaved(unittest.TestCase):
    def test_probe_json_holds_every_field_and_reads_back(self):
        probe, _ = probed(context())
        decision = probe.pop("decision")
        self.assertEqual(Probe.from_json(probe).to_json(), probe, "probe.json reads back into the same Probe")
        self.assertEqual((probe["bash"]["version"], probe["claude_code_version"], probe["os"]),
                         ("1.2.3", "2.1.281", "win32"), "the tools, the Claude Code version and the OS")
        self.assertIsNone(decision.user_message, "a clean probe says nothing to the user")

    def test_the_data_folder_is_made_before_the_first_write(self):
        ctx = context()
        probed(ctx)
        self.assertIn(DATA, ctx.fs.folders, "a fresh install has no data folder yet, so the probe makes it")

    def test_windows_gets_the_cut_and_the_halving_and_macos_neither(self):
        windows, _ = probed(context(WINDOWS))
        macos, _ = probed(context(MACOS))
        self.assertEqual((windows["transport_budget"], windows["halving"]), (session_probe.WINDOWS_CUT, True),
                         "on Windows the Bash tool cuts long commands and halves backslashes")
        self.assertEqual((macos["transport_budget"], macos["halving"]), (None, None),
                         "on macOS nothing was measured, so both stay None")

    def test_a_release_that_fixes_the_cut_retires_it(self):
        with mock.patch.object(session_probe, "FIXED_IN", "2.1.200"):
            probe, _ = probed(context())
        self.assertEqual((probe["transport_budget"], probe["halving"]), (None, None),
                         "from the fixed release on, neither rule applies")

    def test_the_dirty_files_are_absolute(self):
        status = GitStatus((StatusEntry("src/a.py", " ", "M"), StatusEntry("new.txt", "?", "?")))
        probe, _ = probed(context(git=FakeGit(root=ROOT, status=status)))
        self.assertEqual(probe["dirty_at_start"], [str(ROOT / "src/a.py"), str(ROOT / "new.txt")],
                         "task 19 reads the files dirty at session start, as full paths")

    def test_git_that_cannot_answer_leaves_the_dirty_files_unknown(self):
        broken = FakeGit(root=ROOT)
        broken.status = mock.Mock(side_effect=GitError("git timed out"))
        probe, _ = probed(context(git=broken))
        self.assertIsNone(probe["dirty_at_start"], "unknown is None, never an empty list that means clean")


class TheShellDefaults(unittest.TestCase):
    def test_windows_gets_utf8_and_english_tool_output(self):
        _, written = probed(context(WINDOWS))
        self.assertEqual(written, b"export PYTHONUTF8=1\nexport PYTHONIOENCODING=utf-8\n"
                                  b"export DOTNET_CLI_UI_LANGUAGE=en\nexport VSLANG=1033\n",
                         "every later Bash call starts with these")

    def test_macos_gets_utf8_only(self):
        _, written = probed(context(MACOS))
        self.assertEqual(written, b"export PYTHONUTF8=1\nexport PYTHONIOENCODING=utf-8\n",
                         "the Windows tool settings stay off macOS")

    def test_a_second_session_start_adds_nothing_and_keeps_other_hooks_lines(self):
        ctx = context(files={ENV_FILE: b"export OTHER=1"})
        probed(ctx)
        probed(ctx)
        self.assertEqual(ctx.fs.files[ENV_FILE].splitlines()[:2], [b"export OTHER=1", b"export PYTHONUTF8=1"],
                         "another hook's line stays first, and ours follow it once")
        self.assertEqual(ctx.fs.files[ENV_FILE].count(b"PYTHONUTF8"), 1,
                         "a resumed session adds no duplicate")

    def test_no_env_file_writes_only_the_probe(self):
        ctx = context(env={"CLAUDE_ENV_FILE": ""})
        probed(ctx)
        self.assertEqual(ctx.fs.writes, [DATA / "probe.json"],
                         "without CLAUDE_ENV_FILE only probe.json is written")

    def test_a_name_a_shell_cannot_export_is_left_out_and_named(self):
        ctx = context(MACOS)
        env = {"checks.session.probe.env": {"GOOD": "1", "BAD-NAME": "1", "NUMBER": 3}}
        probe, written = probed(replace(ctx, config=Config({**ctx.config.values, **env})))
        self.assertEqual(written, b"export GOOD=1\n", "only a valid name with a string value is exported")
        self.assertIn("BAD-NAME, NUMBER", probe["decision"].user_message,
                      "the user hears which were left out")

    def test_a_value_is_quoted_for_the_shell(self):
        lines, _ = session_probe.export_lines({"A": "x y'z"})
        self.assertEqual(lines, [b"export A='x y'\"'\"'z'\n"], "spaces and quotes survive the shell")


class OnlyTheUserSetsTheDefaults(unittest.TestCase):
    def test_a_project_file_cannot_set_the_shell_defaults(self):
        raw = {"checks": {"session.probe": {"env": {"PYTHONSTARTUP": "evil.py"}}}}
        errors = validate(raw, Scope.PROJECT, all_keys(KEYS), Path("io-guard.json"))
        self.assertTrue(errors and "checks.session.probe.env" in errors[0].key,
                        "a project's io-guard.json could run a program through the environment (D24)")
        self.assertEqual(validate(raw, Scope.USER, all_keys(KEYS), Path("config.json")), (),
                         "the user's own config.json may set them")


if __name__ == "__main__":
    unittest.main()
