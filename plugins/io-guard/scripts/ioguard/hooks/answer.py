"""An Outcome as the JSON answer Claude Code reads for each hook event.

For PreToolUse the verdict and the user's rewrite mode decide the shape, as docs/design/architecture.md,
section 6, tabulates. A shell rewrite's mode is refuse, ask or allow, and a refusal outranks an ask, which
outranks an allow. A file tool's rewrite carries the conformed input and no permission decision, so the
harness applies it and still asks, or approves, as it would have for the original call. Every other event
answers with its context lines, and PostToolUse also with the replaced output and the note for the
auto-mode classifier. The outcome's user_message is the systemMessage the user sees.
"""
import json
from collections.abc import Iterable, Mapping
from typing import Any

from ioguard.checks.pipeline import Outcome
from ioguard.lib.decisions import RewriteMode, Verdict
from ioguard.lib.events import Event, HookEvent, Tool
from ioguard.lib.results import render
FILE_TOOLS = frozenset({Tool.EDIT, Tool.WRITE})   # a rewrite leaves the permission decision to the harness


def answer(event: Event, outcome: Outcome, mode: str) -> dict[str, Any]:
    """The hook's answer. mode is the user's rewrite mode for the event's permission mode."""
    specific = hook_output(event, outcome, mode)
    reply: dict[str, Any] = {}
    if specific:
        reply["hookSpecificOutput"] = {"hookEventName": event.kind.value, **specific}
    if outcome.user_message:
        reply["systemMessage"] = outcome.user_message
    return reply


def hook_output(event: Event, outcome: Outcome, mode: str) -> dict[str, Any]:
    match event.kind:
        case HookEvent.PRE_TOOL_USE:
            return pre_tool_use(event, outcome, mode)
        case HookEvent.POST_TOOL_USE:
            return present(additionalContext=joined(outcome.context),
                           updatedToolOutput=None if outcome.output_replacement is None
                           else dict(outcome.output_replacement),
                           classifierContext=outcome.classifier_note)
        case HookEvent.STOP:
            return {}
        case _:
            return present(additionalContext=joined(outcome.context))


def pre_tool_use(event: Event, outcome: Outcome, mode: str) -> dict[str, Any]:
    rewritten = bool(outcome.rewrites)
    notes = tuple(f"{rewrite.code.value}: {rewrite.note}" for rewrite in outcome.rewrites)
    updated = dict(outcome.tool_input) if rewritten else None
    if rewritten and event.tool in FILE_TOOLS and outcome.verdict < Verdict.ASK:
        return present(updatedInput=updated, additionalContext=joined((*notes, *outcome.context)))
    shape = max(outcome.verdict, RewriteMode(mode).verdict if rewritten else Verdict.OBSERVE)
    match shape:
        case Verdict.DENY if outcome.verdict is Verdict.DENY:
            return {"permissionDecision": "deny", "permissionDecisionReason": refusal(outcome)}
        case Verdict.DENY:
            fields = frozenset().union(*(rewrite.fields for rewrite in outcome.rewrites))
            reason = joined((*notes, *outcome.context, rerun(event, outcome.tool_input, fields)))
            return {"permissionDecision": "deny", "permissionDecisionReason": reason}
        case Verdict.ASK:
            return present(permissionDecision="ask", updatedInput=updated,
                           permissionDecisionReason=joined((*notes, *outcome.context)))
        case Verdict.ALLOW if rewritten:
            return present(permissionDecision="allow", updatedInput=updated,
                           additionalContext=joined((*notes, *outcome.context)))
    return present(additionalContext=joined(outcome.context))


def refusal(outcome: Outcome) -> str:
    """The refusing check's results, then the lines of the checks that ran before it."""
    refused = next(decision for decision in outcome.decisions if decision.verdict is Verdict.DENY)
    reason = joined((*(render(result) for result in refused.results), *outcome.context))
    return reason or f"io-guard's {refused.check_id} check refused this call."


def rerun(event: Event, tool_input: Mapping[str, Any], fields: frozenset[str]) -> str:
    """What the model runs instead, when the user's mode refuses a rewritten call."""
    if fields == {"command"}:
        return f"Run this command instead, exactly as written:\n{tool_input['command']}"
    changed = {key: tool_input.get(key) for key in sorted(fields)}
    return f"Call {event.tool_name} again with these fields: {json.dumps(changed, ensure_ascii=False)}"


def joined(lines: Iterable[str]) -> str | None:
    return "\n".join(lines) or None


def present(**fields: Any) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if value is not None}
