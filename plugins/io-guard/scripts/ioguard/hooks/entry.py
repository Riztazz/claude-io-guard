"""One hook event in, the harness answer out: read the event, run the pipeline, shape the answer.

run_event never raises. An event io-guard cannot read answers {}. A bug past the pipeline's own fail-open
answers {} too, logs GUARD_ERROR with the traceback, and names the failure to the user once per session (D7).
"""
import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from ioguard.checks.pipeline import Outcome, Pipeline
from ioguard.checks.registry import Registry, default_registry
from ioguard.hooks.answer import answer
from ioguard.lib.context import Context, SessionState, plugin_data
from ioguard.lib.events import Event, Surface
from ioguard.lib.results import Code, Result, render
from ioguard.lib.telemetry import debug_log

log = logging.getLogger("ioguard.hooks")


class LiveContexts:
    """The live Context for each session and project this process serves, built on first use.

    The config and the probe load once per process (docs/design/architecture.md, section 8). A session keeps
    one SessionState across its projects, and shares its warned keys with the session's other io-guard
    processes, so a once-per-session warning goes out once.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.contexts: dict[tuple[Path | None, str, Path], Context] = {}
        self.sessions: dict[tuple[Path | None, str], SessionState] = {}
        self.failed: set[str] = set()           # sessions already told that run_event failed

    def get(self, session_id: str, cwd: Path, registry: Registry) -> Context:
        data = plugin_data(os.environ)
        with self.lock:
            key = (data, session_id, cwd)
            if key not in self.contexts:
                session = self.sessions.setdefault((data, session_id), SessionState.shared(data, session_id))
                built = Context.live(data, cwd, registry.keys())
                if data is not None and built.config.get("telemetry.debug"):
                    debug_log(data / "debug.log")
                self.contexts[key] = replace(built, session=session)
            return self.contexts[key]

    def first_failure(self, session_id: str) -> bool:
        with self.lock:
            if session_id in self.failed:
                return False
            self.failed.add(session_id)
            return True


CONTEXTS = LiveContexts()


def read_event(raw: Mapping[str, Any], surface: Surface) -> Event:
    """The harness JSON of a command hook, or the substituted map of an mcp_tool hook."""
    if surface is Surface.MCP_HOOK:
        return Event.from_fields(raw)
    return Event.from_hook_json(raw, surface)


def run_event(raw: Mapping[str, Any], surface: Surface, ctx: Context | None = None,
              registry: Registry | None = None) -> dict[str, Any]:
    """Runs the pipeline for one hook event and returns the harness answer. ctx and registry default to the
    live context for the event's session and to every check io-guard ships."""
    try:
        event = read_event(raw, surface)
    except Exception as error:
        log.warning("GUARD_ERROR: io-guard could not read a %s event, so it let the call go on. %s",
                    surface.value, error)
        return {}
    try:
        registry = registry or default_registry()
        ctx = ctx or CONTEXTS.get(event.session_id, event.cwd, registry)
        outcome = with_config_message(Pipeline(registry).run(event, ctx), ctx, event.cwd)
        mode = ctx.config.get(f"transport.rewrite_mode.{event.permission_mode.value}")
        return answer(event, outcome, mode)
    except Exception:
        log.exception("GUARD_ERROR: io-guard failed on a %s event and let the call go on.", event.kind.value)
        if not CONTEXTS.first_failure(event.session_id):
            return {}
        message = "io-guard failed on this call and let it go on without its checks."
        result = Result.of(Code.GUARD_ERROR, message, event.tool_name, event.platform.os)
        return {"systemMessage": render(result)}


def with_config_message(outcome: Outcome, ctx: Context, project: Path) -> Outcome:
    """The outcome with the config's one message first, the first time this session answers in the project."""
    message = None if ctx.config_report is None else ctx.config_report.user_message
    if message is None or not ctx.session.first_time(f"config:{project}"):
        return outcome
    return replace(outcome, user_message="\n".join(filter(None, (message, outcome.user_message))))
