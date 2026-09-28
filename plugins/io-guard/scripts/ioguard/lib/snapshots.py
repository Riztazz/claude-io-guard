"""Snapshots: the bytes of a set of files kept in io-guard's folder, so a batch of edits can be undone file by
file, or compared, days later and after a restart.

A snapshot is snapshots/<id>/snapshot.json, naming each file with its SHA-256, beside one blob per file. The
id is a UUIDv4 handle that expires seven days after it was taken, and sweep deletes it then. The manifest is
written last, so a snapshot cut short by a crash has none and is never found. A tag names the task a snapshot
comes before, and find returns the newest live snapshot with that tag in the project.
"""
import hashlib
import json
import shutil
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from ioguard.lib import bytesio

TTL = timedelta(days=7)
MANIFEST = "snapshot.json"


@dataclass(frozen=True)
class Kept:
    path: Path
    sha256: str
    size: int
    blob: str                        # the blob's file name inside the snapshot's folder


@dataclass(frozen=True)
class Snapshot:
    id: str
    tag: str
    project: Path
    created: datetime
    expires: datetime
    files: tuple[Kept, ...]
    folder: Path

    def blob(self, kept: Kept) -> bytes:
        return bytesio.read_bytes(self.folder / kept.blob)


def folder_of(home: Path) -> Path:
    return home / "snapshots"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def take(home: Path, tag: str, project: Path, files: Sequence[tuple[Path, bytes]], now: datetime) -> Snapshot:
    """A new snapshot of files, each a path and its bytes, written to io-guard's folder."""
    snapshot_id = str(uuid.uuid4())
    folder = folder_of(home) / snapshot_id
    folder.mkdir(parents=True)
    kept = []
    for number, (path, data) in enumerate(files):
        blob = f"{number}.bin"
        bytesio.write_atomic(folder / blob, data)
        kept.append(Kept(path, digest(data), len(data), blob))
    snapshot = Snapshot(snapshot_id, tag, project, now, now + TTL, tuple(kept), folder)
    manifest = {"id": snapshot_id, "tag": tag, "project": project.as_posix(), "created": now.isoformat(),
                "expires": snapshot.expires.isoformat(),
                "files": [{"path": each.path.as_posix(), "sha256": each.sha256, "size": each.size,
                           "blob": each.blob} for each in kept]}
    bytesio.write_atomic(folder / MANIFEST, json.dumps(manifest, indent=1).encode("utf-8"))
    return snapshot


def read(folder: Path) -> Snapshot | None:
    """The snapshot in folder, or None when its manifest is missing or cannot be read."""
    try:
        manifest = json.loads(bytesio.read_bytes(folder / MANIFEST).decode("utf-8"))
        files = tuple(Kept(Path(each["path"]), each["sha256"], each["size"], each["blob"])
                      for each in manifest["files"])
        created, expires = (datetime.fromisoformat(manifest[key]) for key in ("created", "expires"))
        return Snapshot(manifest["id"], manifest["tag"], Path(manifest["project"]), created, expires, files,
                        folder)
    except (OSError, ValueError, KeyError, TypeError):
        return None


def every(home: Path) -> list[Snapshot]:
    """Each readable snapshot in io-guard's folder, oldest first."""
    root = folder_of(home)
    if not root.is_dir():
        return []
    found = [snapshot for child in root.iterdir() if child.is_dir() and (snapshot := read(child)) is not None]
    return sorted(found, key=lambda snapshot: snapshot.created)


def find(home: Path, key: str, project: Path, now: datetime) -> Snapshot | None:
    """The live snapshot whose id is key, or else the newest live one tagged key in project."""
    live = [snapshot for snapshot in every(home) if snapshot.expires > now]
    by_id = next((snapshot for snapshot in live if snapshot.id == key), None)
    if by_id is not None:
        return by_id
    tagged = [snapshot for snapshot in live if snapshot.tag == key and snapshot.project == project]
    return tagged[-1] if tagged else None


@dataclass(frozen=True)
class Pending:
    """What a restore of snapshot would do: the files whose bytes differ from the snapshot's, or that are
    gone, the files already as it holds them, and each asked-for path it does not hold."""
    snapshot: Snapshot
    changed: tuple[Kept, ...]
    same: tuple[Kept, ...]
    unknown: tuple[Path, ...]

    def key(self) -> str:
        """The restore's name in the session's asked set: the snapshot and the files it would replace."""
        return self.snapshot.id + "|" + "|".join(sorted(kept.path.as_posix() for kept in self.changed))


def pending(snapshot: Snapshot, wanted: Sequence[Path] | None, read: Callable[[Path], bytes | None],
            case_insensitive: bool) -> Pending:
    """The restore of wanted, or of every file when wanted is None, against the files as read finds them now.
    read gives None for a file that is gone."""
    def name(path: Path) -> str:
        return path.as_posix().casefold() if case_insensitive else path.as_posix()
    held = {name(kept.path): kept for kept in snapshot.files}
    chosen = snapshot.files if wanted is None else tuple(held[name(path)] for path in wanted
                                                         if name(path) in held)
    unknown = () if wanted is None else tuple(path for path in wanted if name(path) not in held)
    changed = tuple(kept for kept in chosen
                    if (data := read(kept.path)) is None or digest(data) != kept.sha256)
    return Pending(snapshot, changed, tuple(kept for kept in chosen if kept not in changed), unknown)


def sweep(home: Path, now: datetime) -> int:
    """Delete every expired snapshot, and say how many went."""
    gone = [snapshot for snapshot in every(home) if snapshot.expires <= now]
    for snapshot in gone:
        shutil.rmtree(snapshot.folder, ignore_errors=True)
    return len(gone)
