"""An Event is the same whether it comes from the harness JSON or from an mcp_tool hook's map."""
import json
import unittest
from pathlib import Path

from ioguard.lib.events import Event, EventError, HookEvent, PermissionMode, Surface, Tool
from ioguard.lib.platform import Platform
from tests.support import events
from tests.support.fixtures import FIXTURES_DIR

WINDOWS = Platform("win32", True)
MACOS = Platform("darwin", True)


def recorded(name: str) -> dict:
    return json.loads((FIXTURES_DIR / "events" / f"{name}.json").read_bytes())


def as_fields(raw: dict) -> dict:
    """The map an mcp_tool hook passes: every value a string, tool_input and tool_response as JSON."""
    fields = {key: str(value) for key, value in raw.items() if not isinstance(value, (dict, list))}
    for key in ("tool_input", "tool_response"):
        if key in raw:
            fields[key] = json.dumps(raw[key], separators=(",", ":"))
    return fields


class EventsFromTheHarness(unittest.TestCase):
    def test_a_recorded_bash_event_reads_its_command(self):
        event = Event.from_hook_json(recorded("pre_tool_use_bash"), Surface.COMMAND_HOOK, WINDOWS)
        self.assertEqual((event.kind, event.tool, event.command),
                         (HookEvent.PRE_TOOL_USE, Tool.BASH, recorded("pre_tool_use_bash")["tool_input"]
                          ["command"]), "a recorded Bash event reads as PreToolUse on Bash with its command")

    def test_a_recorded_edit_event_reads_its_strings_and_path(self):
        event = Event.from_hook_json(recorded("pre_tool_use_edit"), Surface.COMMAND_HOOK, WINDOWS)
        self.assertEqual((event.old_string, event.new_string, event.replace_all, event.file_path.as_posix()),
                         ("alpha beta gamma", "alpha BETA gamma", False, "C:/project/edit.txt"),
                         "a recorded Edit event reads its strings, replace_all and absolute path")

    def test_a_session_start_without_permission_mode_reads_as_default(self):
        event = Event.from_hook_json(recorded("session_start"), Surface.COMMAND_HOOK, WINDOWS)
        self.assertEqual((event.kind, event.permission_mode, event.tool),
                         (HookEvent.SESSION_START, PermissionMode.DEFAULT, Tool.OTHER),
                         "SessionStart carries no permission_mode, so the event reads as default")

    def test_the_transcript_path_is_read_from_either_surface(self):
        raw = recorded("pre_tool_use_edit")
        harness = Event.from_hook_json(raw, Surface.COMMAND_HOOK, WINDOWS)
        mapped = Event.from_fields(as_fields(raw), WINDOWS)
        self.assertEqual((harness.transcript, mapped.transcript), (Path(raw["transcript_path"]),) * 2,
                         "the transcript path arrives as the harness JSON and as the mcp_tool map carry it")

    def test_a_failed_read_carries_its_error(self):
        event = Event.from_hook_json(recorded("post_tool_use_failure_read"), Surface.COMMAND_HOOK, WINDOWS)
        self.assertTrue(event.error.startswith("File does not exist."),
                        "a PostToolUseFailure event carries the tool's error text")

    def test_an_mcp_tool_name_is_other_and_keeps_its_name(self):
        raw = events.pre_tool_use("mcp__plugin_io-guard_io__io_edit", {}, Path("C:/p"))
        event = Event.from_hook_json(raw, Surface.MCP_HOOK, WINDOWS)
        self.assertEqual((event.tool, event.tool_name), (Tool.OTHER, "mcp__plugin_io-guard_io__io_edit"),
                         "an MCP tool is Tool.OTHER and tool_name keeps its full name")

    def test_a_relative_path_is_made_absolute_against_cwd(self):
        raw = {**events.read(Path("x"), Path("x")), "cwd": "/work",
               "tool_input": {"file_path": "sub/../a.txt"}}
        event = Event.from_hook_json(raw, Surface.CLI, MACOS)
        self.assertEqual(event.file_path, Path("/work/a.txt"),
                         "a relative file_path resolves against cwd with .. folded")

    def test_an_unknown_hook_event_is_refused_by_name(self):
        raw = {**events.bash("ls", Path("C:/p")), "hook_event_name": "PermissionDenied"}
        with self.assertRaisesRegex(EventError, "PermissionDenied"):
            Event.from_hook_json(raw, Surface.COMMAND_HOOK, WINDOWS)

    def test_a_missing_cwd_is_refused(self):
        raw = events.bash("ls", Path("C:/p"))
        del raw["cwd"]
        with self.assertRaisesRegex(EventError, "cwd"):
            Event.from_hook_json(raw, Surface.COMMAND_HOOK, WINDOWS)

    def test_tool_input_cannot_be_changed_through_the_event(self):
        event = Event.from_hook_json(events.bash("ls", Path("C:/p")), Surface.COMMAND_HOOK, WINDOWS)
        with self.assertRaises(TypeError, msg="a check never mutates event.tool_input"):
            event.tool_input["command"] = "rm"

    def test_with_tool_input_works_out_the_derived_fields_again(self):
        event = Event.from_hook_json(events.bash("ls", Path("C:/p")), Surface.COMMAND_HOOK, WINDOWS)
        moved = event.with_tool_input({"command": "dir", "description": "x"})
        self.assertEqual((moved.command, event.command), ("dir", "ls"),
                         "with_tool_input gives a new event with a new command and leaves the old one")


class EventsFromAnMcpToolHook(unittest.TestCase):
    def test_every_recorded_event_reads_the_same_from_fields(self):
        for name in ("pre_tool_use_bash", "pre_tool_use_edit", "pre_tool_use_write", "post_tool_use_bash",
                     "post_tool_use_read", "post_tool_use_failure_read", "session_start"):
            with self.subTest(event=name):
                direct = Event.from_hook_json(recorded(name), Surface.MCP_HOOK, WINDOWS)
                built = Event.from_fields(as_fields(recorded(name)), WINDOWS)
                self.assertEqual(
                    (built.kind, built.tool_input, built.tool_response, built.error, built.file_path),
                    (direct.kind, direct.tool_input, direct.tool_response, direct.error,
                     direct.file_path), "an event rebuilt from the mcp_tool map equals the harness event")

    def test_an_empty_new_string_stays_apart_from_a_missing_one(self):
        edit = events.edit(Path("C:/p/a.txt"), "gone", "", Path("C:/p"))
        event = Event.from_fields(as_fields(edit), WINDOWS)
        self.assertEqual((event.new_string, event.replace_all), ("", False),
                         "an Edit that deletes text keeps new_string as the empty string")

    def test_replace_all_true_arrives_as_true(self):
        edit = events.edit(Path("C:/p/a.txt"), "a", "b", Path("C:/p"), replace_all=True)
        self.assertTrue(Event.from_fields(as_fields(edit), WINDOWS).replace_all,
                        "replace_all travels inside tool_input's JSON, so true stays a boolean")

    def test_absent_scalars_arrive_empty_and_read_as_none(self):
        fields = {**as_fields(events.bash("ls", Path("C:/p"))), "agent_id": "", "prompt_id": ""}
        event = Event.from_fields(fields, WINDOWS)
        self.assertEqual((event.agent_id, event.prompt_id), (None, None),
                         "the empty string an absent field substitutes to reads as None")

    def test_tool_input_that_is_not_json_is_refused(self):
        fields = {**as_fields(events.bash("ls", Path("C:/p"))), "tool_input": "{not json"}
        with self.assertRaisesRegex(EventError, "tool_input"):
            Event.from_fields(fields, WINDOWS)


if __name__ == "__main__":
    unittest.main()
