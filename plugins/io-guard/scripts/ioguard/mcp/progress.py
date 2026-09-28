"""What a running io tool call hears from its client, and what it tells it: a cancel token the reader thread
sets when a notifications/cancelled for the call arrives, and a progress reporter for a call whose request
carried a progressToken."""
import threading
import time
from collections.abc import Callable
from typing import Any

INTERVAL_S = 0.5             # the fastest a call sends notifications/progress, twice a second


class CancelToken:
    """Set once, when the client cancels the call. A long tool checks it between steps."""

    def __init__(self) -> None:
        self.event = threading.Event()

    def cancel(self) -> None:
        self.event.set()

    @property
    def cancelled(self) -> bool:
        return self.event.is_set()


class ProgressReporter:
    """Sends notifications/progress for one call, at most once every INTERVAL_S seconds. A call whose
    request carried no progressToken sends none. The progress a caller reports must grow, as MCP asks."""

    def __init__(self, notify: Callable[[dict], None] | None = None, token: Any = None,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.notify, self.token, self.clock = notify, token, clock
        self.last: float | None = None

    def report(self, progress: float, message: str | None = None) -> bool:
        """Send progress, unless the call has no token or the last report was too recent. True when sent."""
        if self.notify is None or self.token is None:
            return False
        now = self.clock()
        if self.last is not None and now - self.last < INTERVAL_S:
            return False
        self.last = now
        params = {"progressToken": self.token, "progress": progress}
        if message:
            params["message"] = message
        self.notify({"jsonrpc": "2.0", "method": "notifications/progress", "params": params})
        return True
