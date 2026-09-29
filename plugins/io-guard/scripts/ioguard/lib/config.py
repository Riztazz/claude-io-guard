"""io-guard's policy, in three layers: defaults in code, the user's config.json, and the project's two files.

Every policy value is a key with its default in code (D16). A later layer overrides an earlier one key by
key. Dictionaries merge, lists replace, and a list key that ends in "extra" appends. A project file overrides
the user's file for that project, with two limits. A key marked project_may_set=False reaches every project,
or approves a command in Claude Code's place as a rewrite mode of allow does, so only the user's file sets
it. A regex in a key marked project_regex that lib.patterns finds could stall
drops the file, since io-guard runs it on every line of output. A file with any error is dropped whole, and
the guard runs on the layers that loaded.
"""
import difflib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any

from ioguard import CONFIG_SCHEMA
from ioguard.lib import bytesio, commands, patterns


class Scope(IntEnum):
    DEFAULTS = 0
    USER = 1
    PROJECT = 2
    PROJECT_LOCAL = 3

    @property
    def project(self) -> bool:
        return self >= Scope.PROJECT


@dataclass(frozen=True)
class ConfigKey:
    type: type                       # bool, int, str, list or dict
    default: Any
    doc: str
    project_may_set: bool = True     # False for a key whose effect reaches every project
    choices: tuple = ()              # the values it takes, or () for any of its type
    shape: Callable[[Any], str | None] | None = None   # what is wrong inside a list or dict value, or None
    project_regex: bool = False      # its strings are regexes, which a project file sets only if bounded
    runs: bool = False               # names a program io-guard starts, or a variable a started program reads,
                                     # so a project's value waits for io.trust and io.config asks to write it


@dataclass(frozen=True)
class ConfigLayer:
    scope: Scope
    path: Path


@dataclass(frozen=True)
class ConfigError:
    file: Path | None
    key: str
    message: str
    nearest: str | None = None
    warning: bool = False            # reported, and the file still loads

    def render(self) -> str:
        where = "defaults" if self.file is None else self.file.as_posix()
        hint = f" The nearest known key is {self.nearest}." if self.nearest else ""
        return f"{where}: {self.key}: {self.message}{hint}"


@dataclass(frozen=True)
class Config:
    values: Mapping[str, Any]        # dotted key to value

    def get(self, key: str) -> Any:
        return self.values[key]

    def check_options(self, check_id: str) -> Mapping[str, Any]:
        prefix = f"checks.{check_id}."
        return MappingProxyType({key[len(prefix):]: value for key, value in self.values.items()
                                 if key.startswith(prefix)})


@dataclass(frozen=True)
class LoadReport:
    config: Config
    errors: tuple[ConfigError, ...]
    loaded: tuple[Path, ...]
    dropped: tuple[Path, ...]
    held: Mapping[str, Any] = MappingProxyType({})   # the project files' values of keys marked runs
    changed: Mapping[str, tuple[Any, Any]] = MappingProxyType({})   # key: (the user's value, the project's)

    @property
    def user_message(self) -> str | None:
        """The one message the user sees: the first dropped file and its first error, then each setting the
        project's files change from the user's own, so a cloned repository never turns a check off
        unseen. A check turned off and the time budget come first, since those skip checks, then the rest
        by key."""
        first = next((error for error in self.errors if not error.warning), None)
        dropped = (f"io-guard ignored {first.file.as_posix()} because of an error in it. {first.render()}"
                   if first else None)

        def first_named(item: tuple[str, tuple[Any, Any]]) -> tuple[bool, str]:
            key, (_, now) = item
            skips = (key.endswith(".enabled") and now is False) or key.startswith("pipeline.")
            return not skips, key

        named = [f"{key} {shown(now)} (yours {shown(was)})"
                 for key, (was, now) in sorted(self.changed.items(), key=first_named)[:CHANGES_NAMED]]
        more = len(self.changed) - len(named)
        changes = (f"This project's .claude/io-guard.json changes {len(self.changed)} of your io-guard "
                   f"settings here: {'; '.join(named)}{f' and {more} more' if more else ''}."
                   if named else None)
        return "\n".join(filter(None, (dropped, changes))) or None


def shown(value: Any) -> str:
    """A setting's value in a message: a list or an object by its size, anything else as JSON."""
    if isinstance(value, list):
        return f"a list of {len(value)}"
    if isinstance(value, Mapping):
        return f"an object of {len(value)}"
    return json.dumps(value, ensure_ascii=True)


def at_least_one(value: int) -> str | None:
    return None if value >= 1 else "The value must be 1 or more."


REWRITE_MODES = ("refuse", "ask", "allow")
REWRITE_DEFAULTS = {"default": "ask", "acceptEdits": "ask", "plan": "ask", "auto": "refuse",
                    "dontAsk": "refuse", "bypassPermissions": "allow"}
GLOBAL_KEYS: dict[str, ConfigKey] = {
    "schema": ConfigKey(int, CONFIG_SCHEMA, "The version of this file's format."),
    "pipeline.soft_ms": ConfigKey(int, 300,
                                  "Milliseconds after which checks that start a program are skipped."),
    "pipeline.hard_ms": ConfigKey(int, 2000, "Milliseconds after which every remaining check is skipped."),
    "transport.budget_bytes": ConfigKey(int, 6000, "Bytes of Bash command, each apostrophe counted as four, "
                                        "past which a body moves to a file or the call is refused."),
    "telemetry.enabled": ConfigKey(bool, True, "Record each decision in io-guard's folder."),
    "io.read.max_bytes": ConfigKey(int, 16 * 1024 * 1024, "The largest file io.read reads, in bytes."),
    "io.read.max_chars": ConfigKey(int, 60_000, "The most characters of a file one io.read returns. The "
                                   "result names the call for the lines after them."),
    "io.edit.max_bytes": ConfigKey(int, 16 * 1024 * 1024, "The largest file io.edit, io.splice and io.append "
                                   "change, in bytes."),
    "io.edit.wait_ms": ConfigKey(int, 5000, "Milliseconds io.edit, io.splice and io.append wait for another "
                                 "io-guard call that is changing the same file."),
    "io.run.timeout_s": ConfigKey(int, 120, "Seconds a run to its end may take when the call names none, "
                                  "after which io-guard stops the program."),
    "io.run.handle_ttl_s": ConfigKey(int, 3600, "Seconds a background run's handle lasts after the program "
                                     "ends."),
    "io.read_log.max_lines": ConfigKey(int, 500, "The most log lines one io.read_log returns. The result "
                                       "names the call for the rest."),
    "io.snapshot.max_files": ConfigKey(int, 5000, "The most files one io.snapshot keeps."),
    "io.snapshot.max_bytes": ConfigKey(int, 512 * 1024 * 1024, "The most bytes one io.snapshot keeps, "
                                       "counting every file."),
    "noise_patterns": ConfigKey(list, [], "Regular expressions for log lines io.read_log leaves out, such as "
                                "^LogTemp: Display:. A line counts when one matches anywhere in it. A "
                                "project's list replaces it.",
                                shape=patterns.list_problem, project_regex=True),
    "telemetry.retention_days": ConfigKey(int, 90, "Days a session's telemetry file is kept after its last "
                                          "line, checked when the io server starts. 0 keeps every file. Only "
                                          "your own config sets it, since every project's telemetry shares "
                                          "one folder.", project_may_set=False),
    "telemetry.debug": ConfigKey(bool, False, "Write tracebacks to the debug log."),
    "io.server.workers": ConfigKey(int, 4, "Threads each session's io server runs tool calls and hooks on, "
                                   "and the session probe measures with, at least 1. At 1, a long io.run "
                                   "holds back every hook until it ends. A change applies from the next "
                                   "session. Only your own config sets it, since one server serves every "
                                   "project a session touches.", project_may_set=False, shape=at_least_one),
    "telemetry.cmd_head_days": ConfigKey(int, 7, "Days a telemetry line keeps the first 200 characters of "
                                         "its command, checked when the io server starts. After that only "
                                         "the program's name stays. 0 keeps them whole. Only your own config "
                                         "sets it.", project_may_set=False),
    "io.saved_days": ConfigKey(int, 7, "Days io-guard keeps the tool results, io.run bodies and logs, and "
                               "command bodies it saves in its folder, checked when the io server starts. 0 "
                               "keeps them. Only your own config sets it, since every project's files share "
                               "one folder.", project_may_set=False),
    "skip_trees": ConfigKey(list, [], "Globs, from the repository root, such as Content/**, whose changes a "
                            "shell command's report leaves out. A project's list replaces it."),
    "verify": ConfigKey(dict, {}, "The command io-guard runs on a file after each Edit or Write, per file "
                        "extension, and per project root for one project only. A project file's commands run "
                        "once you approve them through io.trust.", shape=commands.verify_problem, runs=True),
    "format": ConfigKey(dict, commands.FORMAT_DEFAULT, "The command io.format runs over a file's changed "
                        "lines, per file extension, and per project root for one project only. It reads the "
                        "text on stdin and writes the formatted text on stdout. A project file's commands "
                        "run once you approve them through io.trust.", shape=commands.format_problem,
                        runs=True),
    "invisible_allowed": ConfigKey(list, [], "Characters, as U+00A0, a write may add without a warning, "
                                   "though the Read tool shows them as nothing. A project's list replaces "
                                   "it."),
    "commit_policy.forbid": ConfigKey(list, [], "Texts no git commit message may hold, matched without case, "
                                      "such as Co-Authored-By. A commit whose message holds one is refused. "
                                      "A project's list replaces it."),
    "commit_policy.ascii_only": ConfigKey(bool, False, "Refuse a git commit whose message holds a non-ASCII "
                                          "character."),
    "io.format.timeout_s": ConfigKey(int, 30, "Seconds a format command may take on one file, after which "
                                     "io-guard stops it and io.format writes nothing."),
    "io.dashboard.idle_minutes": ConfigKey(int, 5, "Minutes the settings page's server waits with no open "
                                           "page asking before it stops. 0 keeps it up until the session "
                                           "ends."),
    **{f"transport.rewrite_mode.{mode}": ConfigKey(
        str, default, f"What happens to a rewritten command in the {mode} permission mode. Only your own "
        f"config sets it, since allow approves the command in Claude Code's place.",
        choices=REWRITE_MODES, project_may_set=False) for mode, default in REWRITE_DEFAULTS.items()},
}
ENABLED = ConfigKey(bool, True, "Run this check.")
USER_FILE = "Set it in your own config.json in io-guard's folder, ~/.claude/io-guard."
FILE_LIMIT = 256 * 1024          # bytes: a bigger config file is dropped whole rather than read
CHANGES_NAMED = 8                # the settings a project changes that the message names, the rest counted


def all_keys(check_keys: Mapping[str, Mapping[str, ConfigKey]]) -> dict[str, ConfigKey]:
    """The global keys, and checks.<id>.<name> for each check's keys and its enabled switch."""
    keys = dict(GLOBAL_KEYS)
    for check_id, own in check_keys.items():
        keys[f"checks.{check_id}.enabled"] = ENABLED
        keys.update({f"checks.{check_id}.{name}": key for name, key in own.items()})
    return keys


def defaults(check_keys: Mapping[str, Mapping[str, ConfigKey]] | None = None) -> Config:
    return Config(MappingProxyType({key: spec.default for key, spec in all_keys(check_keys or {}).items()}))


def flatten(raw: Mapping[str, Any], keys: Mapping[str, ConfigKey], prefix: str = "") -> dict[str, Any]:
    """Dotted keys for a nested file. A value whose key is dict-typed stays whole."""
    flat = {}
    for name, value in raw.items():
        dotted = f"{prefix}{name}"
        known = keys.get(dotted)
        if isinstance(value, Mapping) and (known is None or known.type is not dict):
            flat.update(flatten(value, keys, f"{dotted}."))
        else:
            flat[dotted] = value
    return flat


def type_matches(value: Any, expected: type) -> bool:
    if expected is int:
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, expected)


def validate(raw: Any, scope: Scope, keys: Mapping[str, ConfigKey], file: Path | None = None
             ) -> tuple[ConfigError, ...]:
    """Every error in one file: unknown keys, wrong types, values outside a key's choices, and keys or values
    this layer may not set. A file from a newer schema reports unknown keys as warnings."""
    if not isinstance(raw, Mapping):
        return (ConfigError(file, "(file)", "The file must hold a JSON object."),)
    newer = type_matches(raw.get("schema"), int) and raw["schema"] > CONFIG_SCHEMA
    errors = []
    for key, value in flatten(raw, keys).items():
        spec = keys.get(key)
        if spec is None:
            nearest = next(iter(difflib.get_close_matches(key, list(keys), n=1, cutoff=0.6)), None)
            errors.append(ConfigError(file, key, "io-guard has no such key.", nearest, warning=newer))
        elif not type_matches(value, spec.type):
            errors.append(ConfigError(file, key, f"The value must be a {spec.type.__name__}, not "
                                                 f"{type(value).__name__}."))
        elif spec.choices and value not in spec.choices:
            errors.append(ConfigError(file, key, f"The value must be one of {', '.join(spec.choices)}."))
        elif scope.project and not spec.project_may_set:
            errors.append(ConfigError(file, key, f"A project file may not set this key. {USER_FILE}"))
        elif spec.shape is not None and (problem := spec.shape(value)):
            errors.append(ConfigError(file, key, problem))
        elif scope.project and spec.project_regex and (problem := unbounded(value)):
            errors.append(ConfigError(file, key, problem))
    return tuple(errors)


def unbounded(value: Any) -> str | None:
    """The first regex in a project file's value that could stall a line's match, as patterns.problem says."""
    return next((found for text in patterns.leaves(value) if (found := patterns.problem(text))), None)


def merge(base: Mapping[str, Any], over: Mapping[str, Any]) -> dict[str, Any]:
    """over's keys win, except that a dict merges into the base dict and a list ending in "extra" appends."""
    merged = dict(base)
    for key, value in over.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        elif isinstance(value, list) and key.endswith("extra") and isinstance(merged.get(key), list):
            merged[key] = [*merged[key], *value]
        else:
            merged[key] = value
    return merged


def read_file(path: Path) -> tuple[Any, ConfigError | None]:
    """The file's JSON, or the error that drops it: over FILE_LIMIT, not UTF-8, or not JSON."""
    data = bytesio.read_bytes(path, FILE_LIMIT + 1)
    if len(data) > FILE_LIMIT:
        return None, ConfigError(path, "(file)", f"The file is over {FILE_LIMIT // 1024} KB, the most "
                                                 f"io-guard reads of a config file.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        return None, ConfigError(path, "(file)",
                                 f"The file is not UTF-8: {error.reason} at byte {error.start}.")
    try:
        return json.loads(text), None
    except json.JSONDecodeError as error:
        return None, ConfigError(path, "(file)", f"The file is not JSON: {error.msg} at line {error.lineno}, "
                                                 f"column {error.colno}.")
    except (ValueError, RecursionError) as error:
        return None, ConfigError(path, "(file)", f"The file is JSON io-guard cannot read: {error}.")


def load(layers: Sequence[ConfigLayer], check_keys: Mapping[str, Mapping[str, ConfigKey]]) -> LoadReport:
    """Merge the layer files that exist over the defaults. A file with an error is left out whole. A project
    file's values of keys marked runs are held apart, merged with each other, for the caller to merge once the
    user approved them. The report names each value the project files change from the user's."""
    keys = all_keys(check_keys)
    values = dict(defaults(check_keys).values)
    users: dict[str, Any] | None = None
    held: dict[str, Any] = {}
    errors, loaded, dropped = [], [], []
    for layer in layers:
        if not layer.path.is_file():
            continue
        raw, unreadable = read_file(layer.path)
        found = (unreadable,) if unreadable else validate(raw, layer.scope, keys, layer.path)
        errors.extend(found)
        if any(not error.warning for error in found):
            dropped.append(layer.path)
            continue
        flat = {key: value for key, value in flatten(raw, keys).items() if key in keys}
        if layer.scope.project:
            users = dict(values) if users is None else users
            held = merge(held, {key: value for key, value in flat.items() if keys[key].runs})
            flat = {key: value for key, value in flat.items() if not keys[key].runs}
        values = merge(values, flat)
        loaded.append(layer.path)
    changed = {key: (users.get(key), value) for key, value in values.items()
               if users is not None and value != users.get(key)}
    return LoadReport(Config(MappingProxyType(values)), tuple(errors), tuple(loaded), tuple(dropped),
                      MappingProxyType(held), MappingProxyType(changed))
