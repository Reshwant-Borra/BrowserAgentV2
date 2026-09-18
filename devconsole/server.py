"""Local Developer Console server: stdlib `http.server`, localhost only.

Routes: `/` serves the static page; `/api/<name>` calls the matching view
in `devconsole.views` with query parameters and returns its JSON. The
server holds no state and makes no decisions.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import views

STATIC = Path(__file__).parent / "static" / "index.html"


def _int(qs: dict, key: str, default: int = 0) -> int:
    return int(qs.get(key, [default])[0])


def _str(qs: dict, key: str, default: str = "") -> str:
    return qs.get(key, [default])[0]


ROUTES = {
    "scenarios": lambda qs: views.scenarios(),
    "m1": lambda qs: views.m1_view(_str(qs, "scenario"), _int(qs, "seed")),
    "m2": lambda qs: views.m2_view(_str(qs, "case"), _int(qs, "seed")),
    "m3": lambda qs: views.m3_view(_str(qs, "scenario"), _int(qs, "seed")),
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 (stdlib naming)
        url = urlparse(self.path)
        if url.path == "/":
            return self._send(200, STATIC.read_bytes(), "text/html; charset=utf-8")
        name = url.path.removeprefix("/api/")
        if name not in ROUTES:
            return self._send(404, b'{"error": "not found"}', "application/json")
        try:
            body = ROUTES[name](parse_qs(url.query))
        except (KeyError, ValueError) as exc:
            return self._send(400, json.dumps({"error": f"bad request: {exc}"}).encode(), "application/json")
        self._send(200, json.dumps(body).encode(), "application/json")

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep the terminal quiet
        pass


def make_server(port: int = 8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
