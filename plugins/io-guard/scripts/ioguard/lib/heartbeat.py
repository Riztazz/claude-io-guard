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


@dataclass(frozen=True)
class Heartbeat:
    pid: int
    session: str
    era: str                     # "undecided", "legacy" or "modern"
    started: datetime
    beat: datetime
    stopped: datetime | None = None

    def again(self, now: datetime, era: str) -> "Heartbeat":
        return replace(self, beat=now, era=era)

    def encode(self) -> bytes:
        fields = {key: value.isoformat() if isinstance(value, datetime) else value
                  for key, value in asdict(self).items()}
        return (json.dumps(fields) + "\n").encode("ascii")


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
        return Heartbeat(int(raw["pid"]), str(raw["session"]), str(raw["era"]),
                         datetime.fromisoformat(raw["started"]), datetime.fromisoformat(raw["beat"]),
                         None if stopped is None else datetime.fromisoformat(stopped))
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
