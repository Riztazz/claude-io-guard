"""The dashboard page and its JSON API, served on 127.0.0.1 for one io server's session.

The server listens on a free port of 127.0.0.1 alone, in a daemon thread that ends with the io server. Every
request carries the token the page's URL holds, in the token query parameter or the X-IOGuard-Token header,
and a Host header naming 127.0.0.1 and the port. A web page from anywhere else knows neither, so it can
neither read the settings nor change one, and a name that only resolves to this machine cannot reach it
either. A change is a POST of JSON, which a form on another page cannot send.

    GET  /                 the page, ui/dashboard.html
    GET  /api/settings     every setting, what each file sets and what applies
    POST /api/setting      {"key", "scope", "value", "remove"}: the same write as io.config
"""
import hmac
import json
import secrets
import threading
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
    """One running page server: its URL, and the two calls its API makes."""

    def __init__(self, settings: Callable[[], dict], write: Callable[[dict], dict],
                 page: Path = PAGE) -> None:
        self.settings, self.write, self.page = settings, write, page
        self.token = secrets.token_urlsafe(24)
        self.server: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

    @property
    def port(self) -> int:
        return self.server.server_address[1] if self.server else 0

    def start(self) -> str:
        """Listen on a free port and serve in a daemon thread. The URL, with its token."""
        if self.server is None:
            self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self))
            self.server.daemon_threads = True
            threading.Thread(target=self.server.serve_forever, name="io-guard dashboard", daemon=True).start()
        return self.url

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None

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
            return parts.path

        def do_GET(self) -> None:
            path = self.permitted()
            if path == "/":
                self.answer(200, board.page.read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/settings":
                self.json(200, board.settings())
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
