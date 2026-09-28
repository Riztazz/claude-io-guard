"""Handles: the opaque ids io tools give out for work that outlives one call, such as a background run.

A handle is a UUIDv4 with a kind and an expiry, as the MCP guidance on stateful tools asks. Its expiry is
unset while the work it names still runs, and settle sets it when the work ends: a run handle lasts one hour
past its program's end. get raises HandleExpired for an id the store does not hold, or holds past its expiry,
and each tool turns that into HANDLE_EXPIRED with the call that starts the work again. The store keeps
handles in memory, so a run handle ends with the server, while the run's log stays on disk. Task 32's
snapshot handles add a file each, which outlives the server.
"""
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class Handle:
    id: str
    kind: str                        # "run", and later "snapshot"
    created: datetime
    expires: datetime | None         # None while the work it names still runs
    payload: Mapping[str, Any]


class HandleExpired(LookupError):
    """The store holds no live handle by that id and kind."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class HandleStore:
    """The server's handles, safe across its workers."""

    def __init__(self, clock: Callable[[], datetime] = utc_now) -> None:
        self.clock = clock
        self.lock = threading.Lock()
        self.held: dict[str, Handle] = {}

    def create(self, kind: str, payload: Mapping[str, Any]) -> Handle:
        self.sweep()
        handle = Handle(str(uuid.uuid4()), kind, self.clock(), None, dict(payload))
        with self.lock:
            self.held[handle.id] = handle
        return handle

    def get(self, handle_id: str, kind: str) -> Handle:
        now = self.clock()
        with self.lock:
            handle = self.held.get(handle_id)
        if handle is None or handle.kind != kind or (handle.expires is not None and handle.expires <= now):
            raise HandleExpired(handle_id)
        return handle

    def settle(self, handle_id: str, ttl: timedelta) -> None:
        """The work the handle names ended, so it expires ttl from now."""
        with self.lock:
            handle = self.held.get(handle_id)
            if handle is not None and handle.expires is None:
                self.held[handle_id] = replace(handle, expires=self.clock() + ttl)

    def close(self, handle_id: str) -> None:
        with self.lock:
            self.held.pop(handle_id, None)

    def sweep(self) -> int:
        """Drop every expired handle, and say how many went."""
        now = self.clock()
        with self.lock:
            gone = [key for key, handle in self.held.items() if handle.expires is not None
                    and handle.expires <= now]
            for key in gone:
                del self.held[key]
        return len(gone)


STORE = HandleStore()
