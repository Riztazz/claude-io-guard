"""The event builders give what Claude Code really sends, and a temporary project holds the bytes it gets."""
import json
import subprocess
import unittest
from pathlib import Path

from tests.support import events
from tests.support.fixtures import FIXTURES_DIR
from tests.support.project import TemporaryProject

CWD = Path("C:/project")


def recorded(name: str) -> dict:
    return json.loads((FIXTURES_DIR / "events" / f"{name}.json").read_bytes())


class EventBuildersMatchRecordedEvents(unittest.TestCase):
    def assertSameShape(self, built: dict, name: str) -> None:
        real = recorded(name)
        self.assertEqual(sorted(built), sorted(real),
                         f"the builder gives the fields Claude Code sent in {name}")
        if isinstance(real.get("tool_input"), dict):
            self.assertEqual(sorted(built["tool_input"]), sorted(real["tool_input"]),
                             f"the builder gives the tool_input fields Claude Code sent in {name}")
        if isinstance(real.get("tool_response"), dict) and real.get("tool_name") == "Bash":
            self.assertEqual(sorted(built["tool_response"]), sorted(real["tool_response"]),
                             f"the builder gives the tool_response fields Claude Code sent in {name}")

    def test_a_bash_event_has_the_recorded_fields(self):
        self.assertSameShape(events.bash("echo hi", CWD), "pre_tool_use_bash")

    def test_an_edit_event_has_the_recorded_fields(self):
        self.assertSameShape(events.edit(CWD / "a.txt", "old", "new", CWD), "pre_tool_use_edit")

    def test_a_write_event_has_the_recorded_fields(self):
        self.assertSameShape(events.write(CWD / "a.txt", "text", CWD), "pre_tool_use_write")

    def test_a_bash_result_event_has_the_recorded_fields(self):
        built = events.post_tool_use("Bash", {"command": "echo hi", "description": "Run a command"},
                                     events.bash_result("hi"), CWD)
        self.assertSameShape(built, "post_tool_use_bash")

    def test_a_read_result_event_has_the_recorded_fields(self):
        built = events.post_tool_use("Read", {"file_path": str(CWD / "a.txt")}, {"type": "text"}, CWD)
        self.assertSameShape(built, "post_tool_use_read")

    def test_a_failed_read_event_has_the_recorded_fields(self):
        built = events.post_tool_use_failure("Read", {"file_path": str(CWD / "a.txt")},
                                             "File does not exist.", CWD)
        self.assertSameShape(built, "post_tool_use_failure_read")

    def test_a_session_start_event_has_the_recorded_fields(self):
        self.assertSameShape(events.session_start(CWD), "session_start")

    def test_a_powershell_event_names_its_tool(self):
        built = events.powershell("Get-Date", CWD)
        self.assertEqual((built["tool_name"], built["tool_input"]["command"]), ("PowerShell", "Get-Date"),
                         "the PowerShell builder names the PowerShell tool and carries the command")

    def test_a_read_event_carries_the_path(self):
        self.assertEqual(events.read(CWD / "a.txt", CWD)["tool_input"], {"file_path": str(CWD / "a.txt")},
                         "the Read builder carries the file path and nothing else")


class TemporaryProjectHoldsTheGivenBytes(unittest.TestCase):
    def test_files_land_byte_for_byte(self):
        data = b"\xef\xbb\xbfone\r\ntwo\r\n"
        with TemporaryProject({"sub/a.txt": data}) as root:
            self.assertEqual((root / "sub" / "a.txt").read_bytes(), data,
                             "a file in a temporary project holds exactly the bytes the test gave")

    def test_the_folder_is_gone_after_the_block(self):
        with TemporaryProject({"a.txt": b"x"}) as root:
            pass
        self.assertFalse(root.exists(), "the temporary project removes its folder when the block ends")

    def test_git_commits_the_given_bytes_unconverted(self):
        data = b"one\r\ntwo\n"
        with TemporaryProject({"a.txt": data}, git=True) as root:
            done = subprocess.run(["git", "cat-file", "blob", "HEAD:a.txt"], cwd=root, capture_output=True,
                                  timeout=60, check=True)
            self.assertEqual(done.stdout, data, "a git project commits the given bytes with no line-ending "
                                                "conversion")


if __name__ == "__main__":
    unittest.main()
