"""The answer a probe hook gives, by mode. The command hook and the MCP gate tool both answer through here."""
from pathlib import Path

ORIGINAL = "IOPROBE_ORIGINAL"
REWRITTEN = "IOPROBE_REWRITTEN"
WRITE_CONTENT = chr(0xFEFF) + "line one\r\nline two\r\n"


def pre_tool_use(decision: str | None, reason: str | None = None, updated_input: dict | None = None,
                 context: str | None = None) -> dict:
    """A PreToolUse answer. A decision of None leaves permissionDecision out, so the harness decides."""
    out: dict = {"hookEventName": "PreToolUse"}
    if decision is not None:
        out["permissionDecision"] = decision
    if reason is not None:
        out["permissionDecisionReason"] = reason
    if updated_input is not None:
        out["updatedInput"] = updated_input
    if context is not None:
        out["additionalContext"] = context
    return {"hookSpecificOutput": out}


def post_output(event_name: str, **fields) -> dict:
    return {"hookSpecificOutput": {"hookEventName": event_name, **fields}}


def extended_edit(tool_input: dict) -> dict | None:
    """Extend old_string and new_string by the character that follows the anchor in the file."""
    data = Path(tool_input["file_path"]).read_bytes().decode("utf-8")
    old = tool_input["old_string"]
    at = data.find(old)
    if at < 0 or at + len(old) >= len(data):
        return None
    follow = data[at + len(old)]
    return {**tool_input, "old_string": old + follow, "new_string": tool_input["new_string"] + follow}


def answer(mode: str, event: dict, nonce: str) -> dict | None:
    """Return the hook's JSON answer for this event, or None to print nothing."""
    name = event.get("hook_event_name")
    tool = event.get("tool_name")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    command = tool_input.get("command", "")
    match (mode, name, tool):
        case ("rewrite_bash_allow" | "rewrite_bash_ask", "PreToolUse", "Bash") if ORIGINAL in command:
            decision = "allow" if mode == "rewrite_bash_allow" else "ask"
            rewritten = {**tool_input, "command": command.replace(ORIGINAL, REWRITTEN)}
            return pre_tool_use(decision, f"io-probe rewrote the command ({nonce})", rewritten)
        case ("rewrite_write", "PreToolUse", "Write"):
            return pre_tool_use("allow", f"io-probe rewrote the content ({nonce})",
                                {**tool_input, "content": WRITE_CONTENT})
        case ("rewrite_write_quiet", "PreToolUse", "Write"):
            return pre_tool_use(None, updated_input={**tool_input, "content": WRITE_CONTENT})
        case ("edit_trailing", "PreToolUse", "Edit"):
            return pre_tool_use("allow", f"io-probe set new_string ({nonce})",
                                {**tool_input, "old_string": "one = 1", "new_string": "one = "})
        case ("rewrite_edit", "PreToolUse", "Edit"):
            extended = extended_edit(tool_input)
            if extended is None:
                return None
            return pre_tool_use("allow", f"io-probe extended ({nonce})", extended)
        case ("context_read", "PostToolUse", "Read"):
            return post_output("PostToolUse", additionalContext=f"IOPROBE-READ-CONTEXT-{nonce}")
        case ("context_failure", "PostToolUseFailure", _):
            return post_output("PostToolUseFailure", additionalContext=f"IOPROBE-FAILURE-CONTEXT-{nonce}")
        case ("updated_output", "PostToolUse", "Bash"):
            response = event.get("tool_response")
            marker = f"IOPROBE-UPDATED-OUTPUT-{nonce}"
            updated = {**response, "stdout": marker} if isinstance(response, dict) else marker
            return post_output("PostToolUse", updatedToolOutput=updated,
                               classifierContext=f"IOPROBE-CLASSIFIER-CONTEXT-{nonce}")
        case ("allow_all", "PreToolUse", _):
            return pre_tool_use("allow", f"io-probe allows ({nonce})")
        case ("mcp_gate_deny", "PreToolUse", _):
            return pre_tool_use("deny", f"IOPROBE-MCP-DENY-{nonce}")
        case _:
            return None
