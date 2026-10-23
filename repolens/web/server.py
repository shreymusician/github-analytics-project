"""The GitHub Intel web server (standard library only): landing page, accounts, and the app behind a login.

Security, because this process holds users' API keys and can clone repositories:
- accounts: passwords are hashed, sessions are random tokens in an HttpOnly SameSite=Strict cookie (Secure over HTTPS),
  every state-changing request needs the session's CSRF token in a header AND, when the browser sends one, a matching
  Origin; JSON bodies only, size-limited;
- the Host header must be one of the allowed hosts (blocks DNS rebinding and host-header tricks);
- a job can only be read by the user who started it; one running job per user; daily quotas per user;
- users' own API keys are encrypted at rest and never sent back to the page;
- no CORS headers are ever sent; a strict Content-Security-Policy allows only same-origin scripts, styles and fonts;
- static files come only from the static folder and only of allowed types; the page can only ask for GitHub owner/name.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .accounts import SESSION_DAYS, Accounts, AuthError
from .jobs import JobManager
from .service import BadRequest, Service, parse_source

STATIC = Path(__file__).parent / "static"
MAX_BODY = 20_000
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".svg": "image/svg+xml", ".woff2": "font/woff2", ".png": "image/png"}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
PAGES = {"/": "landing.html", "/login": "auth.html", "/signup": "auth.html", "/forgot": "auth.html", "/reset": "auth.html",
         "/app": "app.html"}
_JOB_PATH = re.compile(r"^/api/jobs/([0-9a-f]{12})$")
_MINE_PATH = re.compile(r"^/api/mine/(\d{1,12})$")


def make_server(service: Service, accounts: Accounts, host: str = "127.0.0.1", port: int = 8765, jobs: JobManager | None = None,
                allowed_hosts: set[str] | None = None, secure_cookies: bool = False, trust_proxy: bool = False,
                require_verified: bool = False) -> ThreadingHTTPServer:
    jobs = jobs or JobManager()
    cookie_name = "__Host-rl_session" if secure_cookies else "rl_session"

    class Handler(BaseHTTPRequestHandler):
        server_version = "GitHubIntel"
        sys_version = ""

        # --------------------------------------------------------------- helpers
        def log_message(self, fmt, *args):            # keep the console quiet (and never print query strings)
            pass

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None, cookies: list[str] | None = None) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", CSP)
            if secure_cookies:
                self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            for c in cookies or []:
                self.send_header("Set-Cookie", c)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data, cookies: list[str] | None = None) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", cookies=cookies)

        def _fail(self, code: int, msg: str) -> None:
            self._json(code, {"error": msg})

        def _redirect(self, location: str) -> None:
            self._send(HTTPStatus.FOUND, b"", "text/plain; charset=utf-8", extra={"Location": location})

        def _allowed(self) -> set[str]:
            if allowed_hosts:
                return allowed_hosts
            p = self.server.server_address[1]
            return {f"127.0.0.1:{p}", f"localhost:{p}"}

        def _host_ok(self) -> bool:
            return (self.headers.get("Host") or "") in self._allowed()

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if origin is None:
                return True
            return urlparse(origin).netloc in self._allowed()

        def _ip(self) -> str:
            if trust_proxy:
                fwd = (self.headers.get("X-Forwarded-For") or "").split(",")[-1].strip()
                if fwd:
                    return fwd[:64]
            return self.client_address[0]

        def _session_token(self) -> str | None:
            jar = SimpleCookie()
            try:
                jar.load(self.headers.get("Cookie") or "")
            except Exception:                                      # noqa: BLE001 - a malformed cookie is simply no cookie
                return None
            m = jar.get(cookie_name)
            return m.value if m else None

        def _user(self) -> dict | None:
            return accounts.session(self._session_token())

        def _set_cookie(self, token: str) -> str:
            attrs = f"{cookie_name}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_DAYS * 86400}"
            return attrs + ("; Secure" if secure_cookies else "")

        def _clear_cookie(self) -> str:
            return f"{cookie_name}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0" + ("; Secure" if secure_cookies else "")

        def _page(self, name: str) -> None:
            self._send(HTTPStatus.OK, (STATIC / name).read_bytes(), TYPES[".html"])

        # --------------------------------------------------------------- GET
        def do_GET(self):
            if not self._host_ok():
                return self._fail(HTTPStatus.FORBIDDEN, "Unexpected Host header.")
            url = urlparse(self.path)
            q = parse_qs(url.query)
            path = url.path
            if path == "/healthz":
                return self._json(200, {"ok": True})
            if path in PAGES:
                user = self._user()
                if path == "/app":
                    return self._page("app.html") if user else self._redirect("/login")
                if path not in ("/", "/reset") and user:
                    return self._redirect("/app")
                return self._page(PAGES[path])
            if path == "/verify":
                ok = accounts.verify_email((q.get("token") or [""])[0])
                return self._redirect("/app?verified=1" if ok and self._user() else f"/login?verified={1 if ok else 0}")
            if path.startswith("/static/"):
                f = (STATIC / path[len("/static/"):]).resolve()
                if STATIC.resolve() not in f.parents or f.suffix not in TYPES or not f.is_file():
                    return self._fail(HTTPStatus.NOT_FOUND, "Not found.")
                return self._send(HTTPStatus.OK, f.read_bytes(), TYPES[f.suffix])
            if not path.startswith("/api/"):
                return self._fail(HTTPStatus.NOT_FOUND, "Not found.")
            user = self._user()
            if not user:
                return self._fail(HTTPStatus.UNAUTHORIZED, "Please log in.")
            try:
                if path == "/api/me":
                    return self._json(200, self._me(user))
                if path == "/api/status":
                    return self._json(200, service.status())
                if path == "/api/project":
                    return self._json(200, service.project())
                if path == "/api/reports":
                    mine = [{"path": f"mine:{h['id']}", "group": "Your history", "label": h["target"], "kind": "find" if h["kind"] == "find" else "report",
                             "kb": 0, "created": h["created"]} for h in accounts.history(user["id"])]
                    return self._json(200, mine + service.reports())
                if path == "/api/report":
                    return self._json(200, service.report((q.get("path") or [""])[0]))
                m = _MINE_PATH.match(path)
                if m:
                    row = accounts.get_result(user["id"], int(m.group(1)))
                    return self._json(200, row) if row else self._fail(HTTPStatus.NOT_FOUND, "No such saved result.")
                m = _JOB_PATH.match(path)
                if m:
                    since = (q.get("since") or ["0"])[0]
                    snap = jobs.get(m.group(1), int(since) if since.isdigit() else 0, owner=user["id"])
                    return self._json(200, snap) if snap else self._fail(HTTPStatus.NOT_FOUND, "No such job.")
            except BadRequest as e:
                return self._fail(HTTPStatus.BAD_REQUEST, str(e))
            except Exception:                                      # noqa: BLE001 - never leak internals to the page
                return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, "Something went wrong reading that.")
            return self._fail(HTTPStatus.NOT_FOUND, "Not found.")

        def _me(self, user: dict) -> dict:
            return {"user": {"email": user["email"], "verified": user["verified"]}, "csrf": user["csrf"],
                    "usage": accounts.usage(user["id"]), "keys": accounts.list_keys(user["id"]),
                    "models": service.status()["models"], "require_verified": require_verified,
                    "dev_mail": not accounts.mailer.real}

        # --------------------------------------------------------------- POST
        def _drain(self) -> None:
            """Read and discard a small request body before replying. Answering a POST without reading its body can
            reset the connection on some systems, so the client would see a network error instead of our message."""
            length = self.headers.get("Content-Length") or ""
            if length.isdigit() and 0 < int(length) <= MAX_BODY:
                self.rfile.read(int(length))

        def _body(self) -> dict | None:
            """The JSON object sent, or None after replying with an error."""
            if (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                self._drain()
                self._fail(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send JSON.")
                return None
            length = self.headers.get("Content-Length") or ""
            if not length.isdigit() or int(length) > MAX_BODY:
                self._fail(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Request too large.")
                return None
            try:
                body = json.loads(self.rfile.read(int(length)) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError
            except ValueError:
                self._fail(HTTPStatus.BAD_REQUEST, "Invalid JSON.")
                return None
            return body

        def do_POST(self):
            self.close_connection = True
            if not self._host_ok():
                self._drain()
                return self._fail(HTTPStatus.FORBIDDEN, "Unexpected Host header.")
            if not self._origin_ok():
                self._drain()
                return self._fail(HTTPStatus.FORBIDDEN, "Cross-site request refused.")
            path = urlparse(self.path).path
            if not path.startswith("/api/"):
                self._drain()
                return self._fail(HTTPStatus.NOT_FOUND, "Not found.")
            if path in ("/api/auth/signup", "/api/auth/login", "/api/auth/forgot", "/api/auth/reset"):
                body = self._body()
                return self._auth(path.rsplit("/", 1)[1], body) if body is not None else None
            user = self._user()
            if not user:
                self._drain()
                return self._fail(HTTPStatus.UNAUTHORIZED, "Please log in.")
            if not secrets.compare_digest(self.headers.get("X-CSRF") or "", user["csrf"]):
                self._drain()
                return self._fail(HTTPStatus.FORBIDDEN, "Session check failed. Reload the page.")
            body = self._body()
            if body is None:
                return None
            try:
                return self._act(path, body, user)
            except AuthError as e:
                return self._fail(e.status, str(e))
            except BadRequest as e:
                return self._fail(HTTPStatus.BAD_REQUEST, str(e))
            except Exception:                                      # noqa: BLE001
                return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, "Something went wrong.")

        def _auth(self, action: str, body: dict) -> None:
            ip = self._ip()
            try:
                if action in ("signup", "login"):
                    u = (accounts.signup if action == "signup" else accounts.login)(body.get("email"), body.get("password"), ip)
                    token, _ = accounts.create_session(u["id"])
                    return self._json(200, {"ok": True, "next": "/app", "dev_mail": not accounts.mailer.real and action == "signup"},
                                      cookies=[self._set_cookie(token)])
                if action == "forgot":
                    accounts.forgot(body.get("email"), ip)
                    return self._json(200, {"ok": True, "dev_mail": not accounts.mailer.real})
                accounts.reset_password(body.get("token"), body.get("password"))
                return self._json(200, {"ok": True})
            except AuthError as e:
                return self._fail(e.status, str(e))
            except Exception:                                      # noqa: BLE001
                return self._fail(HTTPStatus.INTERNAL_SERVER_ERROR, "Something went wrong.")

        def _act(self, path: str, body: dict, user: dict) -> None:
            uid = user["id"]
            if path == "/api/auth/logout":
                accounts.logout(self._session_token())
                return self._json(200, {"ok": True}, cookies=[self._clear_cookie()])
            if path == "/api/auth/change-password":
                accounts.change_password(uid, body.get("old"), body.get("new"), self._session_token())
                return self._json(200, {"ok": True})
            if path == "/api/auth/delete-account":
                accounts.delete_account(uid, body.get("password"))
                return self._json(200, {"ok": True}, cookies=[self._clear_cookie()])
            if path == "/api/auth/resend":
                accounts.resend_verification(uid)
                return self._json(200, {"ok": True, "dev_mail": not accounts.mailer.real})
            if path == "/api/feedback":
                row = service.add_feedback(body)
                n = accounts.add_feedback(uid, row["kind"], row["target"], row["rating"], row["goal"], row["note"])
                return self._json(200, {"saved": True, "total": n})
            if require_verified and not user["verified"] and path in ("/api/find", "/api/analyze", "/api/keys"):
                return self._fail(HTTPStatus.FORBIDDEN, "Confirm your email first (check your inbox, or resend from Account).")
            if path == "/api/keys":
                accounts.set_key(uid, body.get("provider"), body.get("key"))
                return self._json(200, {"keys": accounts.list_keys(uid)})
            if path == "/api/keys/delete":
                accounts.delete_key(uid, body.get("provider"))
                return self._json(200, {"keys": accounts.list_keys(uid)})
            if path in ("/api/find", "/api/analyze"):
                if path == "/api/find":
                    goal, lang, top = service.validate_find(body.get("goal"), body.get("language"), body.get("top"))
                    kind, target = "find", goal
                else:
                    kind, target = "analyze", parse_source(str(body.get("source") or ""))
                if jobs.active_for(uid) >= 1:
                    return self._fail(HTTPStatus.TOO_MANY_REQUESTS, "You already have a job running. Wait for it to finish.")
                accounts.count_use(uid, kind)                       # refuses with 429 once today's limit is used
                router = service.router_for(accounts.keys_for_jobs(uid))

                def work(progress):
                    result = (service.find(goal, lang, top, progress, router=router) if kind == "find"
                              else service.analyze(target, progress, router=router))
                    result["saved_id"] = accounts.save_result(uid, kind, target, result)
                    return result
                return self._json(202, {"job": jobs.submit(kind, work, owner=uid)})
            return self._fail(HTTPStatus.NOT_FOUND, "Not found.")

    server = ThreadingHTTPServer((host, port), Handler)
    server.daemon_threads = True
    return server


def serve_in_thread(server: ThreadingHTTPServer) -> threading.Thread:
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return t
