"""io.config: read one setting, or write it into your config.json or the project's .claude/io-guard.json.

A write is checked the way the loader checks the whole file, so a value the file could not load is never
written, and a project file never sets what only the user may (docs/design/architecture.md, section 5). The
file is written whole through write_atomic, under the file lock every io-guard process shares, and each
session's hooks load it again from their next call.
"""
import difflib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ioguard import CONFIG_SCHEMA
from ioguard.checks.registry import default_registry
from ioguard.lib import config_edit, locks
from ioguard.lib.config import ConfigKey, Scope, all_keys, flatten, load, validate, widened
from ioguard.lib.context import Context, config_layers, project_root
from ioguard.lib.results import Code, Fix, Result, callable_name
from ioguard.mcp.toolspec import ToolCall, ToolFailure, ToolSpec, doc

NAME = "io.config"
SCOPES = {"user": Scope.USER, "project": Scope.PROJECT}


@dataclass(frozen=True)
class ConfigInput:
    key: str = doc("The setting, as a dotted key, such as checks.shell.lint.enabled or "
                   "transport.rewrite_mode.auto.")
    value: Any = doc("The new value, as JSON. Leave it out to read the setting.", default=None)
    scope: str = doc("user, for your own config.json in io-guard's folder, or project, for the project's "
                     ".claude/io-guard.json.", default="user")
    remove: bool = doc("Remove the setting from the file, so the layer below it applies.", default=False)


@dataclass(frozen=True)
class ConfigOutput:
    key: str = doc("The setting.")
    scope: str = doc("user or project.")
    file: str = doc("The file the scope names, as a path with forward slashes.")
    about: str = doc("What the setting does.")
    choices: tuple[str, ...] = doc("The values it takes, or empty for any of its type.")
    project_may_set: bool = doc("Whether a project file may set it.")
    before: Any = doc("What the file set it to before the call, or null when the file did not set it.")
    after: Any = doc("What the file sets it to now, or null.")
    applies: Any = doc("The value in force for this project now, after every layer.")
    written: bool = doc("The call changed the file.")

    def render(self) -> str:
        head = f"{self.key} in {self.file}: {json.dumps(self.before)}"
        change = f" -> {json.dumps(self.after)}, written." if self.written else "."
        return (f"{head}{change} In force for this project: {json.dumps(self.applies)}. {self.about}"
                + (f" It takes {', '.join(self.choices)}." if self.choices else ""))


def refused(message: str, ctx: Context, file: Path | None = None, fix: str | None = None) -> ToolFailure:
    advice = fix or "Use a key and a value the message names."
    return ToolFailure(Result.of(Code.CONFIG_REFUSED, message, NAME, ctx.platform.os, file=file,
                                 fix=Fix(callable_name(NAME), {}, advice)))


def file_for(scope: Scope, ctx: Context, root: Path) -> Path:
    if scope is Scope.USER:
        if ctx.data_dir is None:
            raise refused("io-guard has no folder of its own here, so it has no user config.json.", ctx)
        return ctx.data_dir / "config.json"
    return root / ".claude" / "io-guard.json"


def read_raw(file: Path, ctx: Context) -> dict:
    """The file's JSON object, or a new one naming the schema when there is no file yet."""
    if not ctx.fs.exists(file):
        return {"schema": CONFIG_SCHEMA}
    try:
        raw = json.loads(ctx.fs.read_bytes(file).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise refused(f"{file.as_posix()} cannot be read as JSON: {error}.", ctx, file,
                      "Fix the file by hand first, since io-guard ignores it until it loads.") from None
    if not isinstance(raw, dict):
        raise refused(f"{file.as_posix()} holds no JSON object.", ctx, file,
                      "Fix the file by hand first, since io-guard ignores it until it loads.")
    return raw


def problem(new: dict, scope: Scope, keys: dict[str, ConfigKey], file: Path, below: dict) -> str | None:
    """The first error the loader would find in the file as written, or None."""
    errors = [error for error in validate(new, scope, keys, file) if not error.warning]
    if not errors and scope.project:
        errors = list(widened(flatten(new, keys), keys, below, file))
    return errors[0].render() if errors else None


def configure(given: ConfigInput, call: ToolCall) -> ConfigOutput:
    ctx = call.context
    check_keys = default_registry().keys()
    keys = all_keys(check_keys)
    spec, scope = keys.get(given.key), SCOPES.get(given.scope)
    if spec is None:
        nearest = difflib.get_close_matches(given.key, list(keys), n=1, cutoff=0.5)
        hint = f" The nearest is {nearest[0]}." if nearest else ""
        raise refused(f"io-guard has no setting {given.key}.{hint}", ctx)
    if scope is None:
        raise refused(f"scope is {given.scope!r}, and it takes user or project.", ctx)
    root = project_root(call.cwd)
    file = file_for(scope, ctx, root)
    layers = config_layers(ctx.data_dir, root)
    below = load([layer for layer in layers if layer.scope < scope], check_keys).config.values
    change = given.remove or given.value is not None
    with locks.file_lock(file, ctx.data_dir or file.parent):
        raw = read_raw(file, ctx)
        before = config_edit.value_at(raw, given.key)
        new = config_edit.placed(raw, given.key, None if given.remove else given.value) if change else raw
        found = problem(new, scope, keys, file, below) if change else None
        if found is not None:
            raise refused(found, ctx, file)
        written = change and new != raw
        if written:
            ctx.fs.make_folders(file.parent)
            ctx.fs.write_atomic(file, config_edit.encoded(new))
    applies = load(layers, check_keys).config.values.get(given.key)
    return ConfigOutput(given.key, given.scope, file.as_posix(), spec.doc, tuple(map(str, spec.choices)),
                        spec.project_may_set, before, config_edit.value_at(new, given.key), applies, written)


SPECS = (ToolSpec(NAME, "Read or change one io-guard setting",
                  "Reads one io-guard setting, or writes it into your own config.json or the project's "
                  ".claude/io-guard.json, checked as io-guard checks the whole file. Use it to turn a check "
                  "off or on, or to change a rewrite mode or a list. It applies from the next tool call.",
                  ConfigInput, ConfigOutput, read_only=False, destructive=False, idempotent=True,
                  handler=configure),)
