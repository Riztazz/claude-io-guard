"""io.config: read one setting, or write it into your config.json or the project's .claude/io-guard.json.
io.dashboard: the settings page, served on 127.0.0.1 by this io server, which writes through the same call.

A write is checked the way the loader checks the whole file, so a value the file could not load is never
written, and a project file never sets what only the user may (docs/design/architecture.md, section 5). The
file is written whole through write_atomic, under the file lock every io-guard process shares, and each
session's hooks load it again from their next call. A write of a key marked runs into the user's file waits
for the user's yes in Claude Code's permission prompt (checks.trust_ask), which the page cannot show, so the
page refuses such a write. The page server starts on the first io.dashboard call for
a project and runs as long as this io server does.
"""
import difflib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ioguard import CONFIG_SCHEMA
from ioguard.checks.registry import default_registry
from ioguard.checks.trust_ask import config_write, needs_yes
from ioguard.lib import config_edit, locks, telemetry, telemetry_summary
from ioguard.lib.config import FILE_LIMIT, ConfigKey, Scope, all_keys, load, validate
from ioguard.lib.context import Context, config_layers, project_root, trusted
from ioguard.lib.results import Code, Fix, Result, callable_name
from ioguard.mcp.dashboard_http import Dashboard, Rejected
from ioguard.mcp.toolspec import ToolCall, ToolFailure, ToolSpec, doc, structured

log = logging.getLogger("ioguard.mcp")

NAME = "io.config"
SCOPES = {"user": Scope.USER, "project": Scope.PROJECT}
FROM_FILE = "stats-from.json"             # in io-guard's folder: the time the page's stats count from
READ_BY = {"commit_policy": "commit.policy"}      # a global key's first part, and the check that reads it


@dataclass(frozen=True)
class ConfigInput:
    key: str = doc("The setting, as a dotted key, such as checks.shell.lint.enabled or "
                   "transport.rewrite_mode.auto.")
    value: Any = doc("The new value, as JSON. Leave it out to read the setting.", default=None)
    scope: str = doc("user, for every project in your own config.json in io-guard's folder, or project, for "
                     "this project's .claude/io-guard.json, which overrides yours here.", default="user")
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
    data = ctx.fs.read_bytes(file, FILE_LIMIT + 1)
    if len(data) > FILE_LIMIT:
        raise refused(f"{file.as_posix()} is over {FILE_LIMIT // 1024} KB, the most io-guard reads of a "
                      f"config file.", ctx, file, "Make the file smaller by hand first.")
    try:
        raw = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise refused(f"{file.as_posix()} cannot be read as JSON: {error}.", ctx, file,
                      "Fix the file by hand first, since io-guard ignores it until it loads.") from None
    if not isinstance(raw, dict):
        raise refused(f"{file.as_posix()} holds no JSON object.", ctx, file,
                      "Fix the file by hand first, since io-guard ignores it until it loads.")
    return raw


def problem(new: dict, scope: Scope, keys: dict[str, ConfigKey], file: Path) -> str | None:
    """The first error the loader would find in the file as written, or None."""
    errors = [error for error in validate(new, scope, keys, file) if not error.warning]
    return errors[0].render() if errors else None


def setting(ctx: Context, cwd: Path, given: ConfigInput) -> ConfigOutput:
    """Read or write one setting for the project cwd belongs to. io.config and the dashboard both call it."""
    check_keys = default_registry().keys()
    keys = all_keys(check_keys)
    spec, scope = keys.get(given.key), SCOPES.get(given.scope)
    if spec is None:
        nearest = difflib.get_close_matches(given.key, list(keys), n=1, cutoff=0.5)
        hint = f" The nearest is {nearest[0]}." if nearest else ""
        raise refused(f"io-guard has no setting {given.key}.{hint}", ctx)
    if scope is None:
        raise refused(f"scope is {given.scope!r}, and it takes user or project.", ctx)
    root = project_root(cwd)
    file = file_for(scope, ctx, root)
    layers = config_layers(ctx.data_dir, root)
    change = given.remove or given.value is not None
    with locks.file_lock(file, ctx.data_dir or file.parent):
        raw = read_raw(file, ctx)
        before = config_edit.value_at(raw, given.key)
        new = config_edit.placed(raw, given.key, None if given.remove else given.value) if change else raw
        found = problem(new, scope, keys, file) if change else None
        if found is not None:
            raise refused(found, ctx, file)
        written = change and new != raw
        if written:
            ctx.fs.make_folders(file.parent)
            ctx.fs.write_atomic(file, config_edit.encoded(new))
    applies = load(layers, check_keys).config.values.get(given.key)
    return ConfigOutput(given.key, given.scope, file.as_posix(), spec.doc, tuple(map(str, spec.choices)),
                        spec.project_may_set, before, config_edit.value_at(new, given.key), applies, written)


def configure(given: ConfigInput, call: ToolCall) -> ConfigOutput:
    ctx, sent = call.context, vars(given)
    if needs_yes(sent) and not ctx.session.take_ask(call.tool_use_id, config_write(sent), ctx.clock.now()):
        raise ToolFailure(Result.of(Code.CONFIG_ASKED, f"{NAME} wrote nothing, because no permission prompt "
                                    f"on this call put {given.key} to the user.", NAME, ctx.platform.os))
    return setting(ctx, call.cwd, given)


def group_of(key: str) -> str:
    """The heading a setting sits under on the page: its check's id, the id of the check that reads it, or the
    first part of its key."""
    if key.startswith("checks."):
        return key[len("checks."):].rsplit(".", 1)[0]
    head = key.split(".")[0]
    return READ_BY.get(head, head)


def file_state(file: Path, ctx: Context) -> tuple[dict, str | None]:
    """A config file's JSON, or an empty object and the reason it could not be read."""
    try:
        return read_raw(file, ctx), None
    except ToolFailure as failure:
        return {}, failure.result.message


def settings(ctx: Context, cwd: Path) -> dict:
    """Every setting with what the user's file and the project's file set, what applies, and whether the
    project's file may set it, for the dashboard page. Plain JSON, since the page reads it."""
    registry = default_registry()
    check_keys = registry.keys()
    keys = all_keys(check_keys)
    root = project_root(cwd)
    files = {name: file_for(scope, ctx, root) for name, scope in SCOPES.items()}
    groups = {check_id: check_class.meta.description for check_id, check_class in registry.classes.items()}
    states = {name: file_state(file, ctx) for name, file in files.items()}
    config, held = trusted(load(config_layers(ctx.data_dir, root), check_keys), ctx.data_dir, root)
    rows = [{"key": key, "group": group_of(key), "about": spec.doc, "type": spec.type.__name__,
             "choices": list(spec.choices), "default": spec.default, "applies": config.values.get(key),
             "user": config_edit.value_at(states["user"][0], key),
             "project": config_edit.value_at(states["project"][0], key),
             "project_may_set": spec.project_may_set, "waiting": key in held}
            for key, spec in sorted(keys.items()) if key != "schema"]
    return {"project": root.as_posix(), "files": {name: file.as_posix() for name, file in files.items()},
            "errors": {name: error for name, (_, error) in states.items() if error}, "groups": groups,
            "settings": rows}


@dataclass(frozen=True)
class DashboardInput:
    pass


@dataclass(frozen=True)
class DashboardOutput:
    url: str = doc("The page, on 127.0.0.1, with the token it needs.")
    project: str = doc("The project whose settings the page shows beside yours.")
    checks_off: tuple[str, ...] = doc("The checks turned off for this project.")
    note: str = doc("Where to open the page.")

    def render(self) -> str:
        off = ", ".join(self.checks_off) if self.checks_off else "none"
        return f"io-guard's settings page: {self.url}\nChecks off for {self.project}: {off}.\n{self.note}"


BOARD_LOCK = threading.Lock()
BOARDS: dict[Path, Dashboard] = {}


def written(ctx: Context, cwd: Path, given: dict) -> dict:
    """A setting the page sent, written as io.config writes it, as the JSON the page reads."""
    known = {name: given[name] for name in ("key", "scope", "value", "remove") if name in given}
    if needs_yes(known):
        mine = (ctx.data_dir / "config.json").as_posix() if ctx.data_dir else "io-guard's config.json"
        raise Rejected({"code": Code.CONFIG_REFUSED.value,
                        "message": f"{known['key']} names a program io-guard starts, or a variable one "
                                   f"reads, and this page cannot ask you to approve it, so it wrote nothing. "
                                   f"Ask Claude to set it with io.config, which shows the permission prompt, "
                                   f"or edit {mine} yourself."})
    try:
        return structured(setting(ctx, cwd, ConfigInput(**known)))
    except ToolFailure as failure:
        raise Rejected({"code": failure.result.code.value, "message": failure.result.message}) from None


def counted_from(ctx: Context) -> datetime | None:
    """The time the stats count from, which the page's Start from now button set, or None for every line."""
    if ctx.data_dir is None or not ctx.fs.exists(ctx.data_dir / FROM_FILE):
        return None
    try:
        return datetime.fromisoformat(json.loads(ctx.fs.read_bytes(ctx.data_dir / FROM_FILE))["from"])
    except (OSError, ValueError, KeyError, TypeError) as failure:
        log.warning("io-guard ignores %s: %s", ctx.data_dir / FROM_FILE, failure)
        return None


def stats(ctx: Context, root: Path, query: dict) -> dict:
    """The telemetry of the last days, 1 to 90, of this project or of every project, as the page draws it,
    from the time the page counts from, with each code's meaning. Command heads stay on this machine: the page
    is the only reader."""
    try:
        days = min(90, max(1, int(query.get("days", 7))))
    except ValueError:
        days = 7
    whole = query.get("scope") == "all"
    folders = [] if ctx.data_dir is None else [ctx.data_dir]
    project = None if whole else ctx.project_name(root)
    return {**telemetry_summary.page(folders, days, ctx.clock.now(), project, counted_from(ctx)),
            "scope": "all" if whole else "project"}


def count_from(ctx: Context, given: dict) -> dict:
    """Count the stats from now on when given from is "now", or from the first line again when it is null.
    Nothing is deleted, and tools/report.py and tools/measure.py never read the mark."""
    if ctx.data_dir is None:
        raise Rejected({"message": "io-guard has no folder of its own here, so it keeps no stats."})
    if given.get("from") not in ("now", None):
        raise Rejected({"message": 'from is "now" or null.'})
    start = ctx.clock.now().isoformat() if given.get("from") == "now" else None
    ctx.fs.make_folders(ctx.data_dir)
    ctx.fs.write_atomic(ctx.data_dir / FROM_FILE, json.dumps({"from": start}).encode("ascii") + b"\n")
    return {"from": start}


def delete_all(ctx: Context, given: dict) -> dict:
    """Delete every telemetry file, of every project, when given confirm is true, and count from the start
    again. A file another session holds open stays."""
    if given.get("confirm") is not True:
        raise Rejected({"message": "Deleting the telemetry needs confirm set to true."})
    if ctx.data_dir is None:
        return {"deleted": 0, "left": 0}
    gone = telemetry.erase(ctx.data_dir, ctx.clock.now())
    count_from(ctx, {"from": None})
    return {"deleted": len(gone), "left": len(telemetry.session_files(ctx.data_dir))}


def forget(root: Path, board: Dashboard) -> None:
    """Drop a stopped page server, unless a newer one already took its place."""
    with BOARD_LOCK:
        if BOARDS.get(root) is board:
            del BOARDS[root]


def dashboard(given: DashboardInput, call: ToolCall) -> DashboardOutput:
    ctx, root = call.context, project_root(call.cwd)
    with BOARD_LOCK:
        if root not in BOARDS:
            idle_s = ctx.config.get("io.dashboard.idle_minutes") * 60
            gets = {"/api/settings": lambda query: settings(ctx, root),
                    "/api/stats": lambda query: stats(ctx, root, query)}
            posts = {"/api/setting": lambda sent: written(ctx, root, sent),
                     "/api/stats/from": lambda sent: count_from(ctx, sent),
                     "/api/stats/delete": lambda sent: delete_all(ctx, sent)}
            board = Dashboard(gets, posts, idle_s=idle_s, on_stop=lambda: forget(root, board))
            BOARDS[root] = board
        url = BOARDS[root].start()
        minutes = BOARDS[root].idle_s / 60
    rows = settings(ctx, root)["settings"]
    off = tuple(row["group"] for row in rows if row["key"].endswith(".enabled") and row["applies"] is False)
    again = callable_name("io.dashboard")
    stops = (f" The page stops {minutes:g} minutes after it closes, and calling {again} again opens a new "
             f"one." if minutes else "")
    note = ("Open the URL in the desktop app's browser pane, and give it to the user as the Markdown link "
            "[Open io-guard's settings page](URL), token and all, which opens in any browser on this "
            "machine. A change there applies from the next tool call.")
    return DashboardOutput(url, root.as_posix(), off, note + stops)


SPECS = (ToolSpec("io.dashboard", "Open io-guard's settings page",
                  "Starts io-guard's settings page on this machine and returns its URL. The page turns "
                  "checks on or off and changes rewrite modes and lists, in your config or the project's. "
                  "Use it when the user wants to see or change io-guard's settings, then open the URL for "
                  "them.",
                  DashboardInput, DashboardOutput, read_only=True, destructive=False, idempotent=True,
                  handler=dashboard),
         ToolSpec(NAME, "Read or change one io-guard setting",
                  "Reads one io-guard setting, or writes it into your own config.json or the project's "
                  ".claude/io-guard.json, checked as io-guard checks the whole file. Use it to turn a check "
                  "off or on, or to change a rewrite mode or a list. It applies from the next tool call.",
                  ConfigInput, ConfigOutput, read_only=False, destructive=False, idempotent=True,
                  handler=configure),)
