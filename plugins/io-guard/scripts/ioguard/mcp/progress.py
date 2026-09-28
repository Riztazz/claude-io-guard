"""What a running io tool call hears from its client: a cancel token the reader thread sets when a
notifications/cancelled for the call arrives."""
import threading


class CancelToken:
    """Set once, when the client cancels the call. A long tool checks it between steps."""

    def __init__(self) -> None:
        self.event = threading.Event()

    def cancel(self) -> None:
        self.event.set()

    @property
    def cancelled(self) -> bool:
        return self.event.is_set()
