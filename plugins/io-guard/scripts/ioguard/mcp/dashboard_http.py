"""The dashboard page and its JSON API, served on 127.0.0.1 for one io server's session.

The server listens on a free port of 127.0.0.1 alone, in a daemon thread that ends with the io server. Every
request carries the token the page's URL holds, in the token query parameter or the X-IOGuard-Token header,
and a Host header naming 127.0.0.1 and the port. A web page from anywhere else knows neither, so it can
neither read the settings nor change one, and a name that only resolves to this machine cannot reach it
either. A change is a POST of JSON, which a form on another page cannot send.

    GET  /                 the page, ui/dashboard.html
    GET  /api/settings     every setting, what each file sets and what applies
    GET  /api/ping         nothing, from an open page, so the server knows it is still used
    GET  /api/stats        ?days=7&scope=project|all: what io-guard fixed, warned about and refused
    POST /api/setting      {"key", "scope", "value", "remove"}: the same write as io.config

The server stops once no request came for io.dashboard.idle_minutes, and the next io.dashboard starts another.
"""
import hmac
import json
import secrets
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

PAGE = Path(__file__).resolve().parents[3] / "ui" / "dashboard.html"
BODY_LIMIT = 64 * 1024
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
           "Content-Security-Policy": "default-src 'self'; style-src 'unsafe-inline'; "
                                      "script-src 'unsafe-inline'; frame-ancestors 'none'"}


class Rejected(Exception):
    """A setting the write refused, with the JSON the page shows."""

    def __init__(self, answer: dict) -> None:
        super().__init__(answer.get("message", ""))
        self.answer = answer


class Dashboard:
    """One running page server: its URL, the two calls its API makes, and how long it waits unasked.

    With idle_s above 0, a watcher stops the server once no request has come for idle_s seconds, and calls
    on_stop, so the next io.dashboard starts a new one. The open page asks every 30 seconds."""

    def __init__(self, settings: Callable[[], dict], write: Callable[[dict], dict], page: Path = PAGE,
                 idle_s: float = 0.0, on_stop: Callable[[], None] | None = None,
                 stats: Callable[[dict], dict] | None = None) -> None:
        self.settings, self.write, self.page, self.stats = settings, write, page, stats
        self.idle_s, self.on_stop = idle_s, on_stop
        self.token = secrets.token_urlsafe(24)
        self.server: ThreadingHTTPServer | None = None
        self.last = time.monotonic()
        self.lock = threading.Lock()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

    @property
    def port(self) -> int:
        return self.server.server_address[1] if self.server else 0

    def start(self) -> str:
        """Listen on a free port and serve in a daemon thread. The URL, with its token."""
        with self.lock:
            self.last = time.monotonic()
            if self.server is None:
                self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self))
                self.server.daemon_threads = True
                threading.Thread(target=self.server.serve_forever, name="io-guard dashboard",
                                 daemon=True).start()
                if self.idle_s > 0:
                    threading.Thread(target=self.watch, name="io-guard dashboard idle", daemon=True).start()
            return self.url

    def stop(self) -> None:
        with self.lock:
            server, self.server = self.server, None
        if server is not None:
            server.shutdown()
            server.server_close()

    def touch(self) -> None:
        self.last = time.monotonic()

    def expired(self, now: float) -> bool:
        """Whether nothing asked the server for idle_s seconds by now, with idle_s above 0."""
        return self.idle_s > 0 and now - self.last >= self.idle_s

    def watch(self) -> None:
        """Stop the server once nothing asked it for idle_s seconds, then tell on_stop."""
        while self.server is not None:
            time.sleep(min(self.idle_s / 4, 5.0))
            if self.server is not None and self.expired(time.monotonic()):
                self.stop()
                if self.on_stop is not None:
                    self.on_stop()
                return

    def allowed(self, host: str | None, token: str | None) -> bool:
        return host == f"127.0.0.1:{self.port}" and hmac.compare_digest(token or "", self.token)


def handler_for(board: Dashboard) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            return None

        def answer(self, status: int, body: bytes, kind: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            for name, value in HEADERS.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def json(self, status: int, value: Any) -> None:
            self.answer(status, json.dumps(value, ensure_ascii=True).encode("ascii"), "application/json")

        def permitted(self) -> str | None:
            """The request's path when its Host and token check out, else None after answering 403."""
            parts = urlsplit(self.path)
            token = self.headers.get("X-IOGuard-Token") or parse_qs(parts.query).get("token", [""])[0]
            if not board.allowed(self.headers.get("Host"), token):
                self.json(403, {"message": "This page needs the URL io.dashboard gave, token and all."})
                return None
            board.touch()
            return parts.path

        def do_GET(self) -> None:
            path = self.permitted()
            if path == "/":
                self.answer(200, board.page.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/settings":
                self.json(200, board.settings())
            elif path == "/api/ping":
                self.json(200, {"idle_s": board.idle_s})
            elif path == "/api/stats" and board.stats is not None:
                query = {name: values[0] for name, values in parse_qs(urlsplit(self.path).query).items()}
                self.json(200, board.stats(query))
            elif path is not None:
                self.json(404, {"message": f"The dashboard has no {path}."})

        def do_POST(self) -> None:
            path = self.permitted()
            if path is None:
                return
            if path != "/api/setting":
                self.json(404, {"message": f"The dashboard has no {path}."})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if not self.headers.get("Content-Type", "").startswith("application/json") or length > BODY_LIMIT:
                self.json(415, {"message": "A setting arrives as JSON, at most 64 KB."})
                return
            try:
                given = json.loads(self.rfile.read(length) or b"{}")
                self.json(200, board.write(given))
            except Rejected as rejected:
                self.json(400, rejected.answer)
            except (ValueError, TypeError) as error:
                self.json(400, {"message": f"The setting could not be read: {error}."})

    return Handler
