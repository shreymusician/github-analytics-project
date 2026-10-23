"""A small local web server (standard library only) for the RepoLens page.

Security, because this process holds your API keys and can clone repositories:
- it listens on 127.0.0.1 only;
- every /api call needs a secret token, which only the page this server serves knows (a different website open in
  your browser cannot guess it, so it cannot make your browser spend your keys or clone repos);
- the Host header must be the local address (blocks DNS-rebinding);
- JSON bodies only, size-limited; static files only from the static folder; no CORS headers are ever sent;
- strict security headers (no external scripts or styles can load); keys are never sent to the page.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .jobs import JobManager
from .service import BadRequest, Service, parse_source

STATIC = Path(__file__).parent / "static"
MAX_BODY = 20_000
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml", ".woff2": "font/woff2", ".png": "image/png"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
_JOB_PATH = re.compile(r"^/api/jobs/([0-9a-f]{12})$")


def make_server(service: Service, host: str = "127.0.0.1", port: int = 8765, token: str | None = None,
                jobs: JobManager | None = None) -> ThreadingHTTPServer:
    token = token or secrets.token_urlsafe(16)
    jobs = jobs or JobManager()

    class Handler(BaseHTTPRequestHandler):
        server_version = "RepoLens"
        sys_version = ""

        # --------------------------------------------------------------- helpers
        def log_message(self, fmt, *args):            # keep the console quiet (and never print query strings)
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", CSP)
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _fail(self, code: int, msg: str) -> None:
            self._json(code, {"error": msg})

        def _host_ok(self) -> bool:
            port_now = self.server.server_address[1]
            return (self.headers.get("Host") or "") in (f"127.0.0.1:{port_now}", f"localhost:{port_now}")

        def _token_ok(self, supplied: str | None) -> bool:
            return bool(supplied) and secrets.compare_digest(supplied, token)

        # --------------------------------------------------------------- GET
        def do_GET(self):
            if not self._host_ok():
                return self._fail(HTTPStatus.FORBIDDEN, "Unexpected Host header.")
            url = urlparse(self.path)
            q = parse_qs(url.query)
            if url.path == "/":
                if not self._token_ok((q.get("t") or [None])[0]):
                    return self._send(HTTPStatus.FORBIDDEN, b"Open the link printed in the terminal where RepoLens is running (it contains a secret token).",
                                      "text/plain; charset=utf-8")
                html = (STATIC / "index.html").read_text(encoding="utf-8").replace("__TOKEN__", token)
                return self._send(HTTPStatus.OK, html.encode("utf-8"), TYPES[".html"])
            if url.path.startswith("/static/"):
                name = url.path[len("/static/"):]
                f = (STATIC / name).resolve()
                if STATIC.resolve() not in f.parents or f.suffix not in TYPES or not f.is_file():
                    return self._fail(HTTPStatus.NOT_FOUND, "Not found.")
                return self._send(HTTPStatus.OK, f.read_bytes(), TYPES[f.suffix])
            if not url.path.startswith("/api/"):
                return self._fail(HTTPStatus.NOT_FOUND, "Not found.")
            if not self._token_ok(self.headers.get("X-Token")):
                return self._fail(HTTPStatus.FORBIDDEN, "Missing or wrong token.")
            try:
                if url.path == "/api/status":
                    return self._json(200, service.status())
                if url.path == "/api/project":
                    return self._json(200, service.project())
                if url.path == "/api/reports":
                    return self._json(200, service.reports())
                if url.path == "/api/report":
                    return self._json(200, service.report((q.get("path") or [""])[0]))
                m = _JOB_PATH.match(url.path)
                if m:
                    since = (q.get("since") or ["0"])[0]
                    snap = jobs.get(m.group(1), int(since) if since.isdigit() else 0)
                    return self._json(200, snap) if snap else self._fail(HTTPStatus.NOT_FOUND, "No such job.")
            except BadRequest as e:
                return self._fail(HTTPStatus.BAD_REQUEST, str(e))
            except Exception:                                      # noqa: BLE001 - never leak internals to the page
                return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, "Something went wrong reading that.")
            return self._fail(HTTPStatus.NOT_FOUND, "Not found.")

        # --------------------------------------------------------------- POST
        def _drain(self) -> None:
            """Read and discard a small request body before replying. Answering a POST without reading its body can
            reset the connection on some systems, so the client would see a network error instead of our message."""
            length = self.headers.get("Content-Length") or ""
            if length.isdigit() and 0 < int(length) <= MAX_BODY:
                self.rfile.read(int(length))

        def do_POST(self):
            self.close_connection = True
            if not self._host_ok():
                self._drain()
                return self._fail(HTTPStatus.FORBIDDEN, "Unexpected Host header.")
            if not self._token_ok(self.headers.get("X-Token")):
                self._drain()
                return self._fail(HTTPStatus.FORBIDDEN, "Missing or wrong token.")
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                self._drain()
                return self._fail(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send JSON.")
            length = self.headers.get("Content-Length") or ""
            if not length.isdigit() or int(length) > MAX_BODY:
                return self._fail(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request too large.")
            try:
                body = json.loads(self.rfile.read(int(length)) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                return self._fail(HTTPStatus.BAD_REQUEST, "Invalid JSON.")
            path = urlparse(self.path).path
            try:
                if path == "/api/find":
                    goal, lang, top = service.validate_find(body.get("goal"), body.get("language"), body.get("top"))
                    return self._json(202, {"job": jobs.submit("find", lambda progress: service.find(goal, lang, top, progress))})
                if path == "/api/analyze":
                    source = parse_source(str(body.get("source") or ""))      # reject bad input now, not inside the job
                    return self._json(202, {"job": jobs.submit("analyze", lambda progress: service.analyze(source, progress))})
                if path == "/api/feedback":
                    return self._json(200, service.add_feedback(body))
            except BadRequest as e:
                return self._fail(HTTPStatus.BAD_REQUEST, str(e))
            except Exception:                                      # noqa: BLE001
                return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, "Something went wrong.")
            return self._fail(HTTPStatus.NOT_FOUND, "Not found.")

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    server.token = token                                           # type: ignore[attr-defined]
    return server


def serve_in_thread(server: ThreadingHTTPServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t
