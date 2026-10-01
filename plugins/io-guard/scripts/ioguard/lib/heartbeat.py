"""The io server's heartbeat: a small JSON file the server rewrites every few seconds while it runs.

The file is sessions/<session>.alive in io-guard's folder. It names the server's process, its MCP era,
when it started, when it last wrote, and when it stopped, if it stopped cleanly. A beat that has gone old with
no stop is a server that died, which a command hook can see even though the server cannot say so itself.

A server that never started writes no heartbeat. Claude Code records a plugin server that failed to start in
its own mcp-needs-auth-cache.json, and skips it in every session for 15 minutes after, so skipped_since reads
that file too. Its format is Claude Code's own and undocumented, and the live-server-down probe checks it.
"""
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum

FRESH_S = 10        # a beat this young is a running server, since the server writes one every 5 seconds


class Era(Enum):
    """The MCP era the io server answers in, decided once per process."""
    UNDECIDED = "undecided"
    LEGACY = "legacy"          # after initialize
    MODERN = "modern"          # after the first request with a protocol version in _meta


@dataclass(frozen=True)
class Heartbeat:
    pid: int
    session: str
    era: Era
    started: datetime
    beat: datetime
    stopped: datetime | None = None

    def again(self, now: datetime, era: Era) -> Heartbeat:
        return replace(self, beat=now, era=era)

    def encode(self) -> bytes:
        """The file's bytes: one line of JSON, the era as its word and each time in ISO 8601."""
        fields = {key: value.isoformat() if isinstance(value, datetime) else value
                  for key, value in asdict(self).items()}
        return (json.dumps({**fields, "era": self.era.value}) + "\n").encode("ascii")


def skipped_since(cache: bytes, server: str, default_ttl_s: float) -> tuple[datetime, datetime] | None:
    """When Claude Code recorded server as failing to start, and when it tries it again, from its
    mcp-needs-auth-cache.json. None when the cache names no such failure."""
    try:
        entry = json.loads(cache.decode("utf-8")).get(server)
        failed = datetime.fromtimestamp(entry["timestamp"] / 1000, timezone.utc)
        ttl_s = entry.get("ttlMs", default_ttl_s * 1000) / 1000
    except (ValueError, KeyError, TypeError, AttributeError, OverflowError, OSError):
        return None
    return failed, failed + timedelta(seconds=ttl_s)


def parse(data: bytes) -> Heartbeat | None:
    """The heartbeat in a file's bytes, or None when they are not one."""
    try:
        raw = json.loads(data.decode("utf-8"))
        stopped = raw.get("stopped")
        return Heartbeat(int(raw["pid"]), str(raw["session"]), Era(raw["era"]),
                         datetime.fromisoformat(raw["started"]), datetime.fromisoformat(raw["beat"]),
                         None if stopped is None else datetime.fromisoformat(stopped))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def quiet(data: bytes, now: datetime, stale_s: float = FRESH_S) -> bool:
    """Whether a heartbeat file's bytes leave nothing to say: no heartbeat in them, a server that stopped
    cleanly, or one that beat within stale_s, which counts as FRESH_S when lower."""
    found = parse(data)
    return found is None or found.stopped is not None or \
        (now - found.beat).total_seconds() <= max(stale_s, FRESH_S)
