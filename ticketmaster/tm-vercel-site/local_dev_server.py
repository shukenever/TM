#!/usr/bin/env python3
"""Serve tm-vercel-site locally and proxy /api/* to tm_viewer_link_registry."""

from __future__ import annotations

import http.server
import os
import socketserver
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND = os.environ.get("TM_VIEWER_BACKEND_URL", "http://127.0.0.1:3919").rstrip("/")
PORT = int(os.environ.get("PORT", "3000"))

# Clean URLs (same as production Vercel rewrites)
CLEAN_ROUTES: dict[str, str] = {
    "/": "/index.html",
    "/login": "/login.html",
    "/my-tickets": "/my-tickets.html",
    "/shop": "/shop.html",
}


class DevHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        if self.path.startswith("/api/"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, X-Shop-Secret, Authorization",
            )
            self.end_headers()
            return
        super().do_OPTIONS()

    def _resolve_local_path(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path or "/"
        if path in CLEAN_ROUTES:
            path = CLEAN_ROUTES[path]
        self.path = path + (("?" + parsed.query) if parsed.query else "")

    def _proxy(self) -> None:
        url = BACKEND + self.path
        body = None
        if self.command in ("POST", "PUT", "PATCH"):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
        req = urllib.request.Request(url, data=body, method=self.command)
        for h in ("Content-Type", "X-Shop-Secret", "Authorization"):
            if h in self.headers:
                req.add_header(h, self.headers[h])
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = resp.read()
                self.send_response(resp.status)
                ct = resp.headers.get("Content-Type")
                if ct:
                    self.send_header("Content-Type", ct)
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            data = e.read()
            self.send_response(e.code)
            ct = e.headers.get("Content-Type") if e.headers else None
            if ct:
                self.send_header("Content-Type", ct)
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            msg = f'{{"ok":false,"error":"proxy_failed","detail":"{e}"}}'.encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(msg)

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self._resolve_local_path()
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._proxy()
            return
        self.send_error(404)


def main() -> None:
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), DevHandler) as httpd:
        print(f"[local-dev] http://127.0.0.1:{PORT}/")
        print(f"[local-dev] shop        http://127.0.0.1:{PORT}/shop.html")
        print(f"[local-dev] my-tickets  http://127.0.0.1:{PORT}/my-tickets")
        print(f"[local-dev] login       http://127.0.0.1:{PORT}/login")
        print(f"[local-dev] proxy /api/* -> {BACKEND}")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
