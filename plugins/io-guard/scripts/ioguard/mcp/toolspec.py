"""The io tools' declarations: each tool's name, its schemas made from dataclasses, its annotations and its
handler, and the registry that lists them in a fixed order and calls them.

A tool's input and output are dataclasses, and their fields and type hints become JSON Schema 2020-12. An
output schema allows extra properties and requires none, because the client validates structuredContent
against it, and a strict schema would turn a new field or a saved result into a failed call. A hook tool
declares neither schema: it takes the map an mcp_tool hook sends and returns its MCP result as it is. The
model sees a tool as mcp__plugin_io-guard_io__ and the name with _ for each dot, and every fix text uses that
name.
"""
import dataclasses
import hashlib
import json
import logging
import time
import traceback
import types
import typing
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ioguard.lib import bytesio
from ioguard.lib.context import Context
from ioguard.lib.events import Surface
from ioguard.lib.platform import detect
from ioguard.lib.results import Code, Result, callable_name, render
from ioguard.lib.telemetry import TelemetryEvent, trace_from
from ioguard.mcp.progress import CancelToken, ProgressReporter

log = logging.getLogger("ioguard.mcp")

RESULT_CHARS = 80_000     # about 20,000 tokens, under the 25,000 Claude Code shows of an MCP result
SAVED_HEAD = 4_000        # the characters of a saved result the answer still shows
NO_DECISION = {"content": [{"type": "text", "text": "{}"}]}


class ToolFailure(Exception):
    """An io tool's expected failure, carrying the Result the model reads."""

    def __init__(self, result: Result) -> None:
        super().__init__(result.message)
        self.result = result


class InvalidArguments(ValueError):
    """Arguments that do not fit a tool's input schema, or a tool that does not exist."""


class ToolCall:
    """What a handler receives beside its input: the session's context, built on first use, the call's
    cancel token and progress reporter, the project folder, and the folder a result too long for one answer
    goes into. The session id, the request's traceparent and the tool use id Claude Code names go into the
    call's telemetry line, so it shares a trace with the hooks of the same tool use."""

    def __init__(self, contexts: Callable[[], Context], cancel: CancelToken, cwd: Path,
                 spill: Path | None, progress: ProgressReporter | None = None, session: str = "io-server",
                 traceparent: str | None = None, tool_use_id: str | None = None) -> None:
        self.contexts, self.cancel, self.cwd, self.spill = contexts, cancel, cwd, spill
        self.progress = progress or ProgressReporter()
        self.session, self.traceparent, self.tool_use_id = session, traceparent, tool_use_id
        self.built: Context | None = None

    @property
    def context(self) -> Context:
        if self.built is None:
            self.built = self.contexts()
        return self.built


@dataclass(frozen=True)
class ToolSpec:
    name: str                              # "io.read"
    title: str
    description: str                       # what it does and when to use it, for tool search
    input: type | None                     # a dataclass, or None for a hook tool, which takes the map as sent
    output: type | None                    # a dataclass, or None for a hook tool, which returns its result
    read_only: bool
    destructive: bool
    idempotent: bool
    handler: Callable[[Any, ToolCall], Any]
    open_world: bool = False
    max_result_chars: int = RESULT_CHARS


def doc(text: str, **fields: Any) -> Any:
    """A dataclass field with a description the schema carries."""
    return dataclasses.field(metadata={"doc": text}, **fields)


def schema(kind: type, loose: bool) -> dict:
    """The JSON Schema of a dataclass. Loose, for an output, allows extra properties and requires none."""
    hints = typing.get_type_hints(kind)
    properties, required = {}, []
    for item in dataclasses.fields(kind):
        entry = type_schema(hints[item.name], loose)
        if "doc" in item.metadata:
            entry["description"] = item.metadata["doc"]
        properties[item.name] = entry
        if item.default is dataclasses.MISSING and item.default_factory is dataclasses.MISSING:
            required.append(item.name)
    found = {"type": "object", "properties": properties, "additionalProperties": loose}
    if required and not loose:
        found["required"] = required
    return found


def type_schema(hint: Any, loose: bool) -> dict:
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin in (typing.Union, types.UnionType):
        kinds = [type_schema(arg, loose) for arg in args if arg is not type(None)]
        return kinds[0] if len(kinds) == 1 else {"anyOf": kinds}
    if hint is bool:
        return {"type": "boolean"}
    if hint is int:
        return {"type": "integer"}
    if hint is float:
        return {"type": "number"}
    if hint in (str, Path):
        return {"type": "string"}
    if origin in (list, tuple, Sequence) and args:
        return {"type": "array", "items": type_schema(args[0], loose)}
    if origin in (dict, Mapping) and len(args) == 2:
        return {"type": "object", "additionalProperties": type_schema(args[1], loose)}
    if hint in (dict, Mapping) or origin in (dict, Mapping):
        return {"type": "object"}
    if dataclasses.is_dataclass(hint):
        return schema(hint, loose)
    return {}


def parse(kind: type, arguments: Mapping[str, Any]) -> Any:
    """The input dataclass from a call's arguments. InvalidArguments names the first field that does not
    fit."""
    hints = typing.get_type_hints(kind)
    known = {item.name: item for item in dataclasses.fields(kind)}
    unknown = sorted(set(arguments) - set(known))
    if unknown:
        raise InvalidArguments(f"{', '.join(unknown)} is not an argument of this tool.")
    values = {}
    for name, item in known.items():
        if name not in arguments:
            if item.default is dataclasses.MISSING and item.default_factory is dataclasses.MISSING:
                raise InvalidArguments(f"The argument {name} is required.")
            continue
        values[name] = value_of(hints[name], arguments[name], name)
    return kind(**values)


def value_of(hint: Any, value: Any, name: str) -> Any:
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin in (typing.Union, types.UnionType):
        if value is None and type(None) in args:
            return None
        return value_of(next(arg for arg in args if arg is not type(None)), value, name)
    expected = {bool: bool, int: int, float: (int, float), str: str, Path: str}.get(hint)
    if expected is not None:
        if not isinstance(value, expected) or (hint is not bool and isinstance(value, bool)):
            raise InvalidArguments(f"The argument {name} must be a {getattr(hint, '__name__', hint)}.")
        return Path(value) if hint is Path else value
    if origin in (list, tuple, Sequence):
        if not isinstance(value, list):
            raise InvalidArguments(f"The argument {name} must be a list.")
        return tuple(value_of(args[0], item, name) for item in value) if args else tuple(value)
    if dataclasses.is_dataclass(hint):
        if not isinstance(value, Mapping):
            raise InvalidArguments(f"The argument {name} must be an object.")
        return parse(hint, value)
    if hint in (dict, Mapping) or origin in (dict, Mapping):
        if not isinstance(value, Mapping):
            raise InvalidArguments(f"The argument {name} must be an object.")
        return {key: value_of(args[1], item, name) if len(args) == 2 else item for key, item in value.items()}
    return value


def structured(value: Any) -> Any:
    """A dataclass as JSON-ready values: paths as strings, tuples as lists."""
    if dataclasses.is_dataclass(value):
        return {item.name: structured(getattr(value, item.name)) for item in dataclasses.fields(value)}
    if isinstance(value, (list, tuple)):
        return [structured(item) for item in value]
    if isinstance(value, Mapping):
        return {key: structured(item) for key, item in value.items()}
    return str(value) if isinstance(value, Path) else value


def failed(result: Result) -> dict:
    """A tool execution error: isError, the result for the model as structuredContent, and its text."""
    return {"content": [{"type": "text", "text": render(result)}], "structuredContent": result.to_json(),
            "isError": True}


class ToolRegistry:
    """Every tool the server offers, in the order they were registered, which tools/list keeps."""

    def __init__(self) -> None:
        self.specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self.specs:
            raise ValueError(f"The tool name {spec.name} is taken.")
        self.specs[spec.name] = spec

    def list(self) -> list[dict]:
        """The tools/list entries."""
        entries = []
        for spec in self.specs.values():
            entry = {"name": spec.name, "title": spec.title, "description": spec.description,
                     "inputSchema": schema(spec.input, loose=False) if spec.input
                     else {"type": "object", "additionalProperties": True},
                     "annotations": {"title": spec.title, "readOnlyHint": spec.read_only,
                                     "destructiveHint": spec.destructive, "idempotentHint": spec.idempotent,
                                     "openWorldHint": spec.open_world}}
            if spec.output is not None:
                entry["outputSchema"] = schema(spec.output, loose=True)
            entries.append(entry)
        return entries

    def markdown(self) -> str:
        """The skill's tool table: each tool the model calls, its job, and the name it calls it by. The hook
        tools, which the model never calls, are left out."""
        rows = [f"| {spec.title} | `{spec.name}` | `{callable_name(spec.name)}` |"
                for spec in self.specs.values() if spec.input is not None]
        return "\n".join(["| Job | Tool | Call it as |", "|---|---|---|", *rows])

    def call(self, name: str, arguments: Mapping[str, Any], call: ToolCall) -> dict:
        """The tools/call result. A bug in a tool answers GUARD_ERROR as a tool error, and a bug in a hook
        tool answers no decision, so the tool call it guards goes on."""
        spec = self.specs.get(name)
        if spec is None:
            raise InvalidArguments(f"io-guard has no tool {name}.")
        if spec.input is None:
            try:
                return spec.handler(arguments, call)
            except Exception:
                log.exception("GUARD_ERROR: io-guard's %s tool failed, so it answered no decision.", name)
                return NO_DECISION
        given = parse(spec.input, arguments)
        started = time.monotonic()
        output, result, error = None, None, None
        if call.cancel.cancelled:
            result = cancelled(name)
        else:
            try:
                output = spec.handler(given, call)
            except ToolFailure as failure:
                result = failure.result
            except InvalidArguments:
                raise
            except Exception as bug:
                trace = traceback.format_exc()
                log.error("GUARD_ERROR: io-guard's %s tool failed.\n%s", name, trace)
                result = Result.of(Code.GUARD_ERROR, f"{name} failed inside io-guard.", name, detect().os)
                error = f"{type(bug).__name__} {hashlib.sha256(trace.encode()).hexdigest()[:12]}"
            else:
                result = cancelled(name) if call.cancel.cancelled else None
        recorded(spec, given, call, (time.monotonic() - started) * 1000, output, result, error)
        return bounded(spec, output, call) if result is None else failed(result)


def cancelled(name: str) -> Result:
    return Result.of(Code.CANCELLED, f"The client cancelled this {name} call.", name, detect().os)


def recorded(spec: ToolSpec, given: Any, call: ToolCall, latency_ms: float, output: Any,
             result: Result | None, error: str | None) -> None:
    """One telemetry line for an io tool call: the tool, the code of a failure, the time it took, the file's
    extension and the bytes it wrote, and no content (section 9). A line that cannot be written is logged,
    and the call answers as it would have."""
    try:
        ctx = call.context
        named = getattr(given, "path", None) or next(iter(getattr(given, "paths", None) or ()), None)
        written = getattr(output, "written_bytes", None)
        ctx.telemetry.record(TelemetryEvent(
            ts=ctx.clock.now(), session=call.session, event="tools/call", surface=Surface.MCP_TOOL.value,
            platform=ctx.platform.os, project=call.cwd.name or None, tool=spec.name,
            code=None if result is None else result.code.value,
            severity=None if result is None else result.severity.value, latency_ms=round(latency_ms, 1),
            error=error, tool_use_id=call.tool_use_id, trace=trace_from(call.tool_use_id, call.traceparent),
            file_ext=Path(named).suffix or None if isinstance(named, str) and named else None,
            bytes=written() if written else None))
    except Exception:
        log.exception("io-guard could not record the telemetry line of a %s call.", spec.name)


def bounded(spec: ToolSpec, output: Any, call: ToolCall) -> dict:
    """The result for an output, with a text too long for one answer saved to a file and named instead."""
    content = structured(output)
    text = output.render() if hasattr(output, "render") else json.dumps(content, ensure_ascii=False)
    if len(text) + len(json.dumps(content)) <= spec.max_result_chars:
        return {"content": [{"type": "text", "text": text}], "structuredContent": content}
    head = text[:SAVED_HEAD]
    if call.spill is None:
        note = f"[io-guard left out {len(text) - len(head):,} characters of this result]"
        return {"content": [{"type": "text", "text": f"{head}\n{note}"}],
                "structuredContent": {"head": head, "chars": len(text)}}
    path = call.spill / f"{spec.name}-{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}.txt"
    call.spill.mkdir(parents=True, exist_ok=True)
    bytesio.write_atomic(path, text.encode("utf-8"))
    note = f"[io-guard: the whole result, {len(text):,} characters, is in {path.as_posix()}]"
    return {"content": [{"type": "text", "text": f"{head}\n{note}"}],
            "structuredContent": {"saved": path.as_posix(), "chars": len(text), "head": head}}
