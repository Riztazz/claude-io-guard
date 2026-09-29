"""Hook events shaped like the ones Claude Code sends, for Bash, PowerShell, Edit, Write and Read.

The fields match the events task 03's probes recorded from Claude Code 2.1.281 and 2.1.283, which are kept in
tests/fixtures/events/. test_support holds the builders to them.
"""
from pathlib import Path

SESSION_ID = "00000000-0000-4000-8000-000000000000"
TOOL_USE_ID = "toolu_01TEST"
TRANSCRIPT = Path.home() / ".claude" / "projects" / "project" / f"{SESSION_ID}.jsonl"   # Claude Code's place


def base(hook_event_name: str, cwd: Path, permission_mode: str = "default") -> dict:
    """The fields every tool event carries."""
    return {
        "session_id": SESSION_ID,
        "prompt_id": SESSION_ID,
        "transcript_path": str(TRANSCRIPT),
        "cwd": str(cwd),
        "scratchpad_dir": str(cwd / ".scratchpad"),
        "permission_mode": permission_mode,
        "hook_event_name": hook_event_name,
    }


def pre_tool_use(tool_name: str, tool_input: dict, cwd: Path, **fields) -> dict:
    return {**base("PreToolUse", cwd), "tool_name": tool_name, "tool_input": tool_input,
            "tool_use_id": TOOL_USE_ID, **fields}


def post_tool_use(tool_name: str, tool_input: dict, tool_response: dict, cwd: Path, **fields) -> dict:
    return {**base("PostToolUse", cwd), "tool_name": tool_name, "tool_input": tool_input,
            "tool_response": tool_response, "tool_use_id": TOOL_USE_ID, "duration_ms": 1, **fields}


def post_tool_use_failure(tool_name: str, tool_input: dict, error: str, cwd: Path, **fields) -> dict:
    return {**base("PostToolUseFailure", cwd), "tool_name": tool_name, "tool_input": tool_input,
            "error": error, "is_interrupt": False, "tool_use_id": TOOL_USE_ID, "duration_ms": 1, **fields}


def session_start(cwd: Path, source: str = "startup") -> dict:
    event = base("SessionStart", cwd)
    del event["prompt_id"], event["permission_mode"]
    return {**event, "source": source}


def bash(command: str, cwd: Path, **fields) -> dict:
    return pre_tool_use("Bash", {"command": command, "description": "Run a command"}, cwd, **fields)


def powershell(command: str, cwd: Path, **fields) -> dict:
    return pre_tool_use("PowerShell", {"command": command, "description": "Run a command"}, cwd, **fields)


def edit(path: Path, old: str, new: str, cwd: Path, replace_all: bool = False, **fields) -> dict:
    tool_input = {"file_path": str(path), "old_string": old, "new_string": new, "replace_all": replace_all}
    return pre_tool_use("Edit", tool_input, cwd, **fields)


def write(path: Path, content: str, cwd: Path, **fields) -> dict:
    return pre_tool_use("Write", {"file_path": str(path), "content": content}, cwd, **fields)


def read(path: Path, cwd: Path, **fields) -> dict:
    return pre_tool_use("Read", {"file_path": str(path)}, cwd, **fields)


def bash_result(stdout: str, stderr: str = "") -> dict:
    """The tool_response a Bash call returns: the shape task 03 recorded."""
    return {"stdout": stdout, "stderr": stderr, "interrupted": False, "isImage": False,
            "noOutputExpected": False}
