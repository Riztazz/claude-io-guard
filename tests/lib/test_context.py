"""Context.fake gives in-memory ports a test controls. Context.live builds the real ones from disk."""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from ioguard.lib.context import (ASK_LIFETIME, SNAPSHOTS_KEPT, Context, LiveFs, Probe, SessionState, Snapshot,
                                 claude_folder, home_folder, memory_file, project_root)
from ioguard.lib.fakes import FakeClock, FakeFs
from ioguard.lib.git import Git
from ioguard.lib.platform import detect


class FakeContexts(unittest.TestCase):
    def test_the_fake_file_system_serves_the_given_bytes(self):
        ctx = Context.fake(files={Path("C:/p/a.txt"): b"one\r\n"})
        self.assertEqual(ctx.fs.read_bytes(Path("C:/p/a.txt")), b"one\r\n",
                         "a fake context's file system holds exactly the bytes a test gives it")

    def test_a_missing_fake_file_raises_like_a_real_one(self):
        with self.assertRaises(FileNotFoundError, msg="the fake file system has no silent empty file"):
            Context.fake().fs.read_bytes(Path("C:/p/nothing.txt"))

    def test_the_fake_clock_moves_only_when_told(self):
        clock = FakeClock()
        before = clock.monotonic()
        clock.advance(250)
        self.assertAlmostEqual(clock.monotonic() - before, 0.25,
                               msg="the fake clock advances by milliseconds")

    def test_any_field_can_be_replaced_by_name(self):
        session = SessionState()
        self.assertIs(Context.fake(session=session).session, session, "an override replaces the field")

    def test_a_fake_write_is_recorded(self):
        fs = FakeFs({})
        fs.write_atomic(Path("C:/p/a.txt"), b"x")
        self.assertEqual((fs.files[Path("C:/p/a.txt")], fs.writes), (b"x", [Path("C:/p/a.txt")]),
                         "the fake file system keeps what was written and the order of writes")


class SessionStateOnce(unittest.TestCase):
    def test_a_key_is_first_time_only_once(self):
        session = SessionState()
        self.assertEqual([session.first_time("w"), session.first_time("w"), session.first_time("v")],
                         [True, False, True], "each warning key is fresh once per session")

    def test_a_snapshot_is_taken_once_and_the_oldest_goes_past_the_limit(self):
        session = SessionState()
        for number in range(SNAPSHOTS_KEPT + 1):
            session.keep_snapshot(f"call{number}", Snapshot(Path(f"C:/p/{number}"), None, None, {}))
        self.assertEqual((session.take_snapshot("call0"), session.take_snapshot("call1").path,
                          session.take_snapshot("call1")), (None, Path("C:/p/1"), None),
                         "the oldest snapshot past the limit is gone, and a snapshot is handed out once")


class AnAskCountsForTheOneCallItWasAskedFor(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.session = SessionState()
        self.session.keep_ask("call1", "git fetch", self.clock.now())

    def test_the_same_call_and_content_is_let_through_once(self):
        self.assertEqual([self.session.take_ask("call1", "git fetch", self.clock.now()),
                          self.session.take_ask("call1", "git fetch", self.clock.now())], [True, False],
                         "one yes lets one call through")

    def test_another_call_no_call_or_other_content_is_not(self):
        for tool_use_id, key in (("call2", "git fetch"), (None, "git fetch"), ("call1", "git push")):
            with self.subTest(tool_use_id=tool_use_id, key=key):
                self.assertFalse(self.session.take_ask(tool_use_id, key, self.clock.now()),
                                 "an ask binds the call's tool use id and its content together")

    def test_an_ask_past_its_lifetime_counts_for_nothing_and_goes(self):
        self.clock.advance(ASK_LIFETIME.total_seconds() * 1000 + 1)
        self.session.keep_ask("call2", "git status", self.clock.now())
        taken = self.session.take_ask("call1", "git fetch", self.clock.now())
        self.assertEqual((list(self.session.asked), taken), (["call2"], False),
                         "a prompt left open too long lets nothing through, and its entry goes")

    def test_a_call_with_no_tool_use_id_is_never_recorded(self):
        self.session.keep_ask(None, "git status", self.clock.now())
        self.assertEqual(list(self.session.asked), ["call1"], "a call that cannot be bound is not kept")


class IoGuardsFolderIsOnePerUser(unittest.TestCase):
    def test_ioguard_home_names_the_folder(self):
        env = {"IOGUARD_HOME": "C:/somewhere/else", "CLAUDE_CONFIG_DIR": "C:/config"}
        self.assertEqual(home_folder(env), Path("C:/somewhere/else"), "IOGUARD_HOME wins over everything")

    def test_without_ioguard_home_the_folder_follows_claude_config_dir(self):
        self.assertEqual(home_folder({"CLAUDE_CONFIG_DIR": "C:/config"}), Path("C:/config") / "io-guard",
                         "a user who moved ~/.claude gets io-guard's folder inside the moved one")

    def test_claude_code_s_folder_follows_the_home_folder_the_environment_names(self):
        for env, expected in (({"USERPROFILE": "C:/Users/u"}, Path("C:/Users/u/.claude")),
                              ({"HOME": "/Users/u"}, Path("/Users/u/.claude")),
                              ({"CLAUDE_CONFIG_DIR": "D:/cfg", "HOME": "/Users/u"}, Path("D:/cfg"))):
            with self.subTest(env=env):
                self.assertEqual(claude_folder(env), expected,
                                 "the environment a caller gives decides, so a test or a hook's own "
                                 "environment sets it")

    def test_with_neither_the_folder_is_io_guard_in_dot_claude(self):
        self.assertEqual(home_folder({}), Path.home() / ".claude" / "io-guard",
                         "the default is ~/.claude/io-guard, whatever id Claude Code gives the plugin")

    def test_the_suite_never_uses_the_users_own_folder(self):
        self.assertTrue(home_folder(os.environ).is_relative_to(tempfile.gettempdir()),
                        "tests/__init__ points IOGUARD_HOME at a temporary folder for every test")


class AProjectIsTheNearestFolderThatNamesOne(unittest.TestCase):
    def test_the_nearest_config_or_repository_above_the_working_folder(self):
        root = Path(tempfile.mkdtemp(prefix="ioguard-root-"))
        self.addCleanup(shutil.rmtree, root, True)
        for folder in ("app/.claude", "app/src/deep", "app/lib/.git", "app/lib/pkg", "loose/sub"):
            (root / folder).mkdir(parents=True)
        (root / "app" / ".claude" / "io-guard.json").write_bytes(b"{}")
        found = [project_root(root / name) for name in ("app/src/deep", "app/lib/pkg", "loose/sub")]
        self.assertEqual(found, [root / "app", root / "app" / "lib", root / "loose" / "sub"],
                         "a config file or a repository ends the walk, whichever is nearer, and a folder "
                         "under neither is its own project")


class AMemoryNoteLivesInClaudeCodesFolder(unittest.TestCase):
    def test_only_a_markdown_file_in_a_projects_memory_folder_is_a_note(self):
        env, projects = {"CLAUDE_CONFIG_DIR": "C:/config"}, Path("C:/config/projects")
        found = [memory_file(path, env) for path in (
            projects / "C--game" / "memory" / "rule.md", projects / "C--game" / "memory" / "rule.txt",
            projects / "C--game" / "rule.md", Path("C:/game/memory/rule.md"),
            Path.home() / ".claude" / "projects" / "C--game" / "memory" / "rule.md")]
        self.assertEqual(found, [True, False, False, False, False],
                         "a note is projects/<project>/memory/<name>.md in CLAUDE_CONFIG_DIR, and no other")

    def test_claude_codes_folder_follows_claude_config_dir(self):
        self.assertEqual((claude_folder({"CLAUDE_CONFIG_DIR": "C:/config"}), claude_folder({})),
                         (Path("C:/config"), Path.home() / ".claude"), "CLAUDE_CONFIG_DIR, then ~/.claude")


class LiveContexts(unittest.TestCase):
    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="ioguard-data-"))
        self.project = Path(tempfile.mkdtemp(prefix="ioguard-project-"))

    def tearDown(self):
        shutil.rmtree(self.data, ignore_errors=True)
        shutil.rmtree(self.project, ignore_errors=True)

    def test_live_reads_the_user_and_project_layers(self):
        (self.data / "config.json").write_bytes(b'{"pipeline": {"hard_ms": 1500}}')
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "io-guard.json").write_bytes(b'{"pipeline": {"soft_ms": 100}}')
        ctx = Context.live(self.data, self.project)
        self.assertEqual((ctx.config.get("pipeline.hard_ms"), ctx.config.get("pipeline.soft_ms")),
                         (1500, 100), "a live context merges the user file and the project file")
        self.assertIsInstance(ctx.git, Git, "a live context talks to git")
        self.assertIsInstance(ctx.fs, LiveFs, "a live context talks to the file system")

    def test_without_a_probe_file_the_probe_says_what_is_unknown(self):
        probe = Context.live(self.data, self.project).probe
        measured = (probe.os, probe.halving, probe.transport_budget, probe.taken_at)
        self.assertEqual(measured, (detect().os, None, None, None),
                         "before the session probe has run, unmeasured fields are None, never a guess")

    def test_a_live_context_carries_the_environment_and_the_data_folder(self):
        ctx = Context.live(self.data, self.project)
        self.assertEqual((ctx.data_dir, ctx.env.get("PATH")), (self.data, os.environ.get("PATH")),
                         "a check reads both from the context, never from os.environ")

    def test_a_probe_file_is_read_back(self):
        written = {"os": "win32", "bash": {"path": "bash.exe", "version": "5.2"}, "pwsh": None,
                   "python": {"path": "python.exe", "version": "3.14.0"}, "git": None,
                   "console_encoding": "cp1252", "fs_case_insensitive": True, "transport_budget": 6000,
                   "halving": True, "claude_code_version": "2.1.283", "dirty_at_start": [],
                   "taken_at": "2026-09-27T12:00:00+00:00"}
        (self.data / "probe.json").write_bytes(json.dumps(written).encode("ascii"))
        probe = Context.live(self.data, self.project).probe
        self.assertEqual((probe.transport_budget, probe.halving, probe.bash.version), (6000, True, "5.2"),
                         "a live context loads the probe the session probe saved")

    def test_a_probe_file_that_cannot_be_read_counts_as_no_probe(self):
        for data in (b'{"os": "win32"}', b"not json", b"[1, 2]"):
            with self.subTest(data=data):
                (self.data / "probe.json").write_bytes(data)
                probe = Context.live(self.data, self.project).probe
                self.assertEqual((probe.os, probe.taken_at), (detect().os, None),
                                 "a broken probe file is left for the session probe to write again, and "
                                 "never stops the server starting")

    def test_a_path_the_system_rejects_has_no_stat(self):
        (self.project / "file.txt").write_bytes(b"x")
        for path in (self.project / "a?b", self.project / ("x" * 300), self.project / "file.txt" / "x"):
            with self.subTest(path=str(path)[-20:]):
                self.assertIsNone(LiveFs().stat(path), "a name no file can have is a file that is not there")

    def test_live_file_ports_round_trip_bytes(self):
        target = self.project / "a.txt"
        LiveFs().write_atomic(target, b"\xef\xbb\xbfone\r\n")
        self.assertEqual((LiveFs().read_bytes(target), LiveFs().stat(target).size),
                         (b"\xef\xbb\xbfone\r\n", 8), "the live file port writes and reads exact bytes")

    @unittest.skipUnless(sys.platform in ("win32", "darwin"), "the Restart Manager and lsof answer there")
    def test_a_file_nobody_holds_has_no_holder(self):
        (self.project / "free.txt").write_bytes(b"x")
        self.assertEqual(LiveFs().holders(self.project / "free.txt"), (),
                         "the live file port asks the platform, and a free file has no holder")

    def test_an_unprobed_probe_knows_this_python(self):
        import sys
        self.assertEqual(Probe.unprobed(detect()).python.path, sys.executable,
                         "the one thing known before the probe is the Python io-guard runs on")


if __name__ == "__main__":
    unittest.main()
