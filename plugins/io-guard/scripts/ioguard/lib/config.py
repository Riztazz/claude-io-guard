"""io-guard's policy, in four layers: defaults in code, the user's config.json, and two project files.

Every policy value is a key with its default in code (D16). A later layer overrides an earlier one key by
key. Dictionaries merge, lists replace, and a list key that ends in "extra" appends. A project file restricts
and never widens: it cannot set a key marked project_may_set=False, set a value in project_forbids, raise a
number marked project_narrows above the layers below it, or set a regex in a key marked project_regex that
lib.patterns finds could stall. Its list for a key marked project_joins, where a longer list is stricter, adds
to the list below and never drops an entry of it. A file with any error is dropped whole, and the guard runs
on the layers that loaded.
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
    project_may_set: bool = True
    choices: tuple = ()              # the values it takes, or () for any of its type
    project_forbids: tuple = ()      # values a project file may not set
    project_narrows: bool = False    # a project file may lower this number and never raise it
    shape: Callable[[Any], str | None] | None = None   # what is wrong inside a list or dict value, or None
    project_regex: bool = False      # its strings are regexes, which a project file sets only if bounded
    project_joins: bool = False      # a longer list is stricter, so a project's list adds to the one below


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

    @property
    def user_message(self) -> str | None:
        """The one message the user sees: the first dropped file and its first error."""
        first = next((error for error in self.errors if not error.warning), None)
        if first is None:
            return None
        return f"io-guard ignored {first.file.as_posix()} because of an error in it. {first.render()}"


REWRITE_MODES = ("refuse", "ask", "allow")
REWRITE_DEFAULTS = {"default": "ask", "acceptEdits": "ask", "plan": "ask", "auto": "refuse",
                    "dontAsk": "refuse", "bypassPermissions": "allow"}
GLOBAL_KEYS: dict[str, ConfigKey] = {
    "schema": ConfigKey(int, CONFIG_SCHEMA, "The version of this file's format."),
    "pipeline.soft_ms": ConfigKey(int, 300,
                                  "Milliseconds after which checks that start a program are skipped."),
    "pipeline.hard_ms": ConfigKey(int, 2000, "Milliseconds after which every remaining check is skipped."),
    "transport.budget_bytes": ConfigKey(int, 6000, "Bytes of Bash command, each apostrophe counted as four, "
                                        "past which a body moves to a file or the call is refused.",
                                        project_narrows=True),
    "telemetry.enabled": ConfigKey(bool, True, "Record each decision in io-guard's folder.",
                                   project_forbids=(False,)),
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
    "io.snapshot.max_files": ConfigKey(int, 5000, "The most files one io.snapshot keeps.",
                                       project_narrows=True),
    "io.snapshot.max_bytes": ConfigKey(int, 512 * 1024 * 1024, "The most bytes one io.snapshot keeps, "
                                       "counting every file.", project_narrows=True),
    "noise_patterns": ConfigKey(list, [], "Regular expressions for log lines io.read_log leaves out, such as "
                                "^LogTemp: Display:. A line counts when one matches anywhere in it. A "
                                "project's list replaces it.",
                                shape=patterns.list_problem, project_regex=True),
    "telemetry.retention_days": ConfigKey(int, 90, "Days a telemetry file is kept."),
    "telemetry.debug": ConfigKey(bool, False, "Write tracebacks to the debug log."),
    "skip_trees": ConfigKey(list, [], "Globs, from the repository root, such as Content/**, whose changes a "
                            "shell command's report leaves out. A project's list replaces it."),
    "verify": ConfigKey(dict, {}, "The command io-guard runs on a file after each Edit or Write, per file "
                        "extension, and per project root for one project only.", project_may_set=False,
                        shape=commands.verify_problem),
    "format": ConfigKey(dict, commands.FORMAT_DEFAULT, "The command io.format runs over a file's changed "
                        "lines, per file extension, and per project root for one project only. It reads the "
                        "text on stdin and writes the formatted text on stdout.", project_may_set=False,
                        shape=commands.format_problem),
    "invisible_allowed": ConfigKey(list, [], "Characters, as U+00A0, a write may add without a warning, "
                                   "though the Read tool shows them as nothing. A project's list replaces "
                                   "it."),
    "commit_policy.forbid": ConfigKey(list, [], "Texts no git commit message may hold, matched without case, "
                                      "such as Co-Authored-By. A commit whose message holds one is refused.",
                                      project_may_set=False),
    "commit_policy.ascii_only": ConfigKey(bool, False, "Refuse a git commit whose message holds a non-ASCII "
                                          "character.", project_forbids=(False,)),
    "io.format.timeout_s": ConfigKey(int, 30, "Seconds a format command may take on one file, after which "
                                     "io-guard stops it and io.format writes nothing."),
    "io.dashboard.idle_minutes": ConfigKey(int, 5, "Minutes the settings page's server waits with no open "
                                           "page asking before it stops. 0 keeps it up until the session "
                                           "ends.", project_may_set=False),
    **{f"transport.rewrite_mode.{mode}": ConfigKey(
        str, default, f"What happens to a rewritten command in the {mode} permission mode.",
        choices=REWRITE_MODES, project_forbids=("allow",)) for mode, default in REWRITE_DEFAULTS.items()},
}
ENABLED = ConfigKey(bool, True, "Run this check.")
USER_FILE = "Set it in your own config.json in io-guard's folder, ~/.claude/io-guard."


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
        elif scope.project and value in spec.project_forbids:
            errors.append(ConfigError(file, key, f"A project file may not set this key to "
                                                 f"{json.dumps(value)}. {USER_FILE}"))
        elif spec.shape is not None and (problem := spec.shape(value)):
            errors.append(ConfigError(file, key, problem))
        elif scope.project and spec.project_regex and (problem := unbounded(value)):
            errors.append(ConfigError(file, key, problem))
    return tuple(errors)


def unbounded(value: Any) -> str | None:
    """The first regex in a project file's value that could stall a line's match, as patterns.problem says."""
    return next((found for text in patterns.leaves(value) if (found := patterns.problem(text))), None)


def widened(flat: Mapping[str, Any], keys: Mapping[str, ConfigKey], below: Mapping[str, Any],
            file: Path | None) -> tuple[ConfigError, ...]:
    """A project file's raises of a key it may only lower, against the layers loaded below it."""
    return tuple(ConfigError(file, key, f"A project file may lower this number and not raise it past "
                                        f"{below[key]}. {USER_FILE}")
                 for key, value in flat.items()
                 if key in keys and keys[key].project_narrows and value > below[key])


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


def joined(below: list, added: list) -> list:
    """below with each entry of added it lacks appended after it, in added's order."""
    return [*below, *(entry for entry in added if entry not in below)]


def read_file(path: Path) -> tuple[Any, ConfigError | None]:
    try:
        text = bytesio.read_bytes(path).decode("utf-8")
    except UnicodeDecodeError as error:
        return None, ConfigError(path, "(file)",
                                 f"The file is not UTF-8: {error.reason} at byte {error.start}.")
    try:
        return json.loads(text), None
    except json.JSONDecodeError as error:
        return None, ConfigError(path, "(file)", f"The file is not JSON: {error.msg} at line {error.lineno}, "
                                                 f"column {error.colno}.")


def load(layers: Sequence[ConfigLayer], check_keys: Mapping[str, Mapping[str, ConfigKey]]) -> LoadReport:
    """Merge the layer files that exist over the defaults. A file with an error is left out whole."""
    keys = all_keys(check_keys)
    values = dict(defaults(check_keys).values)
    errors, loaded, dropped = [], [], []
    for layer in layers:
        if not layer.path.is_file():
            continue
        raw, unreadable = read_file(layer.path)
        found = (unreadable,) if unreadable else validate(raw, layer.scope, keys, layer.path)
        if not found and layer.scope.project:
            found = widened(flatten(raw, keys), keys, values, layer.path)
        errors.extend(found)
        if any(not error.warning for error in found):
            dropped.append(layer.path)
            continue
        flat = {key: value for key, value in flatten(raw, keys).items() if key in keys}
        if layer.scope.project:
            flat = {key: joined(values[key], value) if keys[key].project_joins else value
                    for key, value in flat.items()}
        values = merge(values, flat)
        loaded.append(layer.path)
    return LoadReport(Config(MappingProxyType(values)), tuple(errors), tuple(loaded), tuple(dropped))
