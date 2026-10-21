"""Browser emulator: python3 -m totem web

A small local server around the same App that drives the real terminal. The
page in totem/web/index.html draws the 80x24 (or 40x24) screen like a green
phosphor monitor and sends key presses back.

    GET  /                          the emulator page
    GET  /api/screen?sid=..&width=  current screen
    POST /api/key  {sid, width, key}  press a key, get the new screen

A slow fetch answers with the loading screen and busy=true; the page then
polls /api/screen until busy is false, just like the real terminal would
show the loading screen first and the result later.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .app import App
from .shop import Shop

PAGE = Path(__file__).parent / "web" / "index.html"
MAX_SESSIONS = 50


class Session:
    def __init__(self, shop: Shop, width: int, loading_delay: float):
        self.loading: list[str] | None = None
        self.worker: threading.Thread | None = None
        self.app = App(shop, width=width, on_loading=self._on_loading,
                       loading_delay=loading_delay)

    def _on_loading(self, rows: list[str]) -> None:
        self.loading = rows

    def busy(self) -> bool:
        return bool(self.worker and self.worker.is_alive())

    def press(self, key: str) -> dict:
        if self.busy():  # one key at a time while the shop is answering
            return self.snapshot()
        self.loading = None
        self.worker = threading.Thread(target=self.app.key, args=(key,), daemon=True)
        self.worker.start()
        while self.worker.is_alive() and self.loading is None:
            self.worker.join(0.02)
        return self.snapshot()

    def snapshot(self) -> dict:
        busy = self.busy()
        rows = self.loading if busy and self.loading else self.app.screen()
        return {"rows": rows, "busy": busy, "width": self.app.w}


class Sessions:
    def __init__(self, shop: Shop, loading_delay: float):
        self.shop, self.loading_delay = shop, loading_delay
        self._items: dict[tuple[str, int], Session] = {}
        self._lock = threading.Lock()

    def get(self, sid: str, width: int) -> Session:
        key = (sid[:64], width if width in (40, 80) else 80)
        with self._lock:
            if key not in self._items:
                if len(self._items) >= MAX_SESSIONS:
                    self._items.pop(next(iter(self._items)))
                self._items[key] = Session(self.shop, key[1], self.loading_delay)
            return self._items[key]


def make_server(shop: Shop, host: str = "127.0.0.1", port: int = 8765,
                loading_delay: float = 0.5) -> ThreadingHTTPServer:
    sessions = Sessions(shop, loading_delay)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data: dict, code: int = 200) -> None:
            self._send(code, json.dumps(data).encode(), "application/json")

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == "/":
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/screen":
                q = parse_qs(url.query)
                sid = q.get("sid", ["default"])[0]
                width = int(q.get("width", ["80"])[0] or 80)
                self._json(sessions.get(sid, width).snapshot())
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self):
            if urlparse(self.path).path != "/api/key":
                return self._send(404, b"not found", "text/plain")
            try:
                length = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(min(length, 4096)) or b"{}")
                key = str(data["key"])
                if not key or (len(key) > 1 and not key.isupper()):
                    raise ValueError("bad key")
            except (ValueError, KeyError, json.JSONDecodeError):
                return self._json({"error": "bad request"}, 400)
            session = sessions.get(str(data.get("sid", "default")),
                                   int(data.get("width", 80) or 80))
            self._json(session.press(key))

    return ThreadingHTTPServer((host, port), Handler)
