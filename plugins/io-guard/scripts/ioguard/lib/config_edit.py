"""One setting placed in a config file's JSON, where the file keeps its neighbours, or removed from it.

A file may nest a dotted key any way the loader reads, such as checks > shell.lint > enabled or checks > shell
> lint > enabled. A new key goes under the longest part of its path the file already holds, and the rest nests
the way the defaults name it: checks, then the check's id, then the option, and one level per dot elsewhere.
A removed key takes each object it leaves empty with it, so the layer below applies again. The user's settings
for one project sit under projects, keyed by the project's folder, and entry_of and with_entry read and write
that one object.
"""
import copy
import json
from typing import Any

from ioguard.lib.config import PROJECTS


def canonical(key: str) -> list[str]:
    """The nesting a new key takes: checks > <check id> > <option>, or one level per dot for the rest."""
    if key.startswith("checks.") and key.count(".") >= 2:
        check_id, option = key[len("checks."):].rsplit(".", 1)
        return ["checks", check_id, option]
    return key.split(".")


def found_path(raw: dict, key: str) -> list[str]:
    """The names the file already holds on key's way down, each the longest one that leads toward it."""
    trail, node, left = [], raw, key
    while isinstance(node, dict) and left:
        leading = [name for name in node if left == name or left.startswith(name + ".")]
        name = max(leading, key=len, default=None)
        if name is None:
            break
        trail.append(name)
        node, left = node[name], left[len(name) + 1:]
    return trail


def path_for(raw: dict, key: str) -> list[str]:
    """Where key lives or would live in raw: its existing part, then the canonical nesting for the rest."""
    trail = found_path(raw, key)
    done = ".".join(trail)
    if done == key:
        return trail
    parts = canonical(key)
    for at in range(len(parts) + 1):
        if ".".join(parts[:at]) == done:
            return trail + parts[at:]
    return trail + key[len(done) + 1 if done else 0:].split(".")


def placed(raw: dict, key: str, value: Any) -> dict:
    """A copy of raw with key set to value, or removed when value is None, and emptied objects pruned."""
    out = copy.deepcopy(raw)
    path = path_for(out, key)
    if value is not None:
        node = out
        for name in path[:-1]:
            if not isinstance(node.get(name), dict):
                node[name] = {}
            node = node[name]
        node[path[-1]] = value
        return out
    chain, node = [], out
    for name in path:
        if not isinstance(node, dict) or name not in node:
            return out
        chain.append((node, name))
        node = node[name]
    parent, name = chain.pop()
    del parent[name]
    while chain and chain[-1][0][chain[-1][1]] == {}:
        parent, name = chain.pop()
        del parent[name]
    return out


def value_at(raw: dict, key: str) -> Any:
    """What the file sets key to, or None when it does not set it."""
    node = raw
    for name in path_for(raw, key):
        if not isinstance(node, dict) or name not in node:
            return None
        node = node[name]
    return node


def entry_of(raw: dict, folder: str) -> dict:
    """The user's settings for the project at folder, under projects, or an empty object."""
    entries = raw.get(PROJECTS)
    entry = entries.get(folder) if isinstance(entries, dict) else None
    return entry if isinstance(entry, dict) else {}


def with_entry(raw: dict, folder: str, entry: dict) -> dict:
    """A copy of raw whose projects entry for folder is entry. An empty entry goes, and projects with it
    when it holds nothing else."""
    out = copy.deepcopy(raw)
    entries = out.get(PROJECTS) if isinstance(out.get(PROJECTS), dict) else {}
    if entry:
        out[PROJECTS] = {**entries, folder: entry}
        return out
    entries.pop(folder, None)
    if entries:
        out[PROJECTS] = entries
    else:
        out.pop(PROJECTS, None)
    return out


def encoded(raw: dict) -> bytes:
    """The file's bytes: two-space JSON, ASCII, with a final newline."""
    return (json.dumps(raw, indent=2, ensure_ascii=True) + "\n").encode("ascii")
