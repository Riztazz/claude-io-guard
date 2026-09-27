"""The replay corpus: every file and shell tool call in a set of Claude Code transcripts, with its result.

Each source is a project's transcript folder, ~/.claude/projects/<encoded path>, read with its subagent
transcripts, and a name the project counts under. The corpus is <out>/<name>.jsonl, one Record per line, and
<out>/index.json with the counts. A record holds the call's whole input, so a replay runs the call as it was,
and the head of its result. A resumed session writes its history into a new transcript, so one call can sit in
several files, and several times in one: each tool use id enters once, and the index counts the copies. The
corpus holds the user's paths and content, so it stays on the machine (D8).
"""
import json
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ioguard.cli.labels import labels

CORPUS_SCHEMA = 1
TOOLS = frozenset({"Bash", "PowerShell", "Edit", "MultiEdit", "Write", "Read", "Grep", "Glob",
                   "NotebookEdit"})
RESULT_CHARS = 2000          # the head of the result text a record keeps
RESPONSE_CHARS = 4000        # the longest string a record keeps inside the structured tool response
RESPONSE_ITEMS = 200         # the longest list it keeps there
MARKERS = (b'"tool_use"', b'"tool_result"', b'"permissionMode"')


@dataclass(frozen=True)
class Record:
    id: str                  # the tool use id
    project: str
    session: str
    agent: bool              # the call came from a subagent's transcript
    ts: str
    version: str | None      # the Claude Code version that ran the call
    cwd: str
    permission_mode: str
    tool: str
    input: dict[str, Any]
    failed: bool
    result: str              # the head of the result text
    result_chars: int
    response: Any            # the structured tool response, its long strings and lists cut
    labels: tuple[str, ...]

    def to_json(self) -> dict:
        return asdict(self) | {"labels": list(self.labels)}

    @classmethod
    def from_json(cls, raw: dict) -> "Record":
        return cls(**(raw | {"labels": tuple(raw["labels"])}))


@dataclass
class Tally:
    records: Counter
    labels: Counter
    unpaired: int = 0
    unreadable: int = 0
    copies: int = 0


def text_of(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(block.get("text", "") for block in content
                         if isinstance(block, dict) and block.get("type") == "text")
    return ""


def cut(value: Any) -> Any:
    """The value with every string past RESPONSE_CHARS and every list past RESPONSE_ITEMS cut short."""
    if isinstance(value, str):
        return value[:RESPONSE_CHARS]
    if isinstance(value, list):
        return [cut(item) for item in value[:RESPONSE_ITEMS]]
    if isinstance(value, dict):
        return {key: cut(item) for key, item in value.items()}
    return value


def read_transcript(path: Path, project: str, tally: Tally) -> Iterator[Record]:
    """The guarded tool calls in one transcript, each with its result. A call with no result is counted and
    dropped, and so is a line that is not JSON."""
    pending: dict[str, tuple[dict, dict, str]] = {}
    mode = "default"
    agent = "subagents" in path.parts
    with path.open("rb") as lines:
        for line in lines:
            if not any(marker in line for marker in MARKERS):
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                tally.unreadable += 1
                continue
            mode = entry.get("permissionMode") or mode
            content = (entry.get("message") or {}).get("content")
            if not isinstance(content, list):
                continue
            blocks = [block for block in content if isinstance(block, dict)]
            results = sum(block.get("type") == "tool_result" for block in blocks)
            for block in blocks:
                if block.get("type") == "tool_use" and block.get("name") in TOOLS:
                    pending[block.get("id")] = (block, entry, mode)
                elif block.get("type") == "tool_result" and block.get("tool_use_id") in pending:
                    use, used_in, used_mode = pending.pop(block["tool_use_id"])
                    response = entry.get("toolUseResult") if results == 1 else None
                    yield record(project, agent, use, used_in, used_mode, block, response)
    tally.unpaired += len(pending)


def record(project: str, agent: bool, use: dict, entry: dict, mode: str, result: dict,
           response: Any) -> Record:
    tool_input = use.get("input") if isinstance(use.get("input"), dict) else {}
    text = text_of(result.get("content"))
    failed = bool(result.get("is_error"))
    return Record(
        id=use.get("id") or "", project=project, session=entry.get("sessionId") or "", agent=agent,
        ts=entry.get("timestamp") or "", version=entry.get("version"), cwd=entry.get("cwd") or "",
        permission_mode=mode, tool=use["name"], input=tool_input, failed=failed, result=text[:RESULT_CHARS],
        result_chars=len(text), response=cut(response),
        labels=labels(use["name"], str(tool_input.get("command") or ""), text, failed))


def build(sources: Sequence[tuple[str, Path]], out: Path) -> dict:
    """Write the corpus for the sources into out, and return its index."""
    out.mkdir(parents=True, exist_ok=True)
    folders: dict[str, list[Path]] = defaultdict(list)
    for name, folder in sources:
        folders[name].append(folder)
    tally = Tally(Counter(), Counter())
    seen: set[str] = set()
    for name, named in folders.items():
        with (out / f"{name}.jsonl").open("wb") as corpus:
            for path in sorted(path for folder in named for path in folder.rglob("*.jsonl")):
                for found in read_transcript(path, name, tally):
                    if found.id in seen:
                        tally.copies += 1
                        continue
                    seen.add(found.id)
                    corpus.write(json.dumps(found.to_json(), ensure_ascii=True).encode("ascii") + b"\n")
                    tally.records[(name, found.tool)] += 1
                    tally.labels.update(found.labels)
    index = {
        "schema": CORPUS_SCHEMA,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {name: [str(folder) for folder in named] for name, named in folders.items()},
        "records": {name: {tool: count for (project, tool), count in sorted(tally.records.items())
                           if project == name} for name in folders},
        "labels": dict(tally.labels.most_common()),
        "unpaired": tally.unpaired,
        "unreadable": tally.unreadable,
        "copies": tally.copies,
    }
    (out / "index.json").write_bytes((json.dumps(index, indent=1) + "\n").encode("ascii"))
    return index


def load(corpus: Path, projects: Sequence[str] = ()) -> Iterator[Record]:
    """Every record in the corpus, or in the named projects only."""
    for path in sorted(corpus.glob("*.jsonl")):
        if projects and path.stem not in projects:
            continue
        with path.open("rb") as lines:
            for line in lines:
                yield Record.from_json(json.loads(line))
