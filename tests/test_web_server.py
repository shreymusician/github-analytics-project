import http.client
import json
import re
import time

import pytest
from cryptography.fernet import Fernet

from repolens.web import server as srv
from repolens.web.accounts import Accounts, Mailer
from repolens.web.service import Service
from tests.test_discover import FakeExt, cand  # noqa: F401

PW = "correct horse battery"


class Client:
    """A tiny browser: keeps cookies, remembers the CSRF token."""

    def __init__(self, port):
        self.port, self.cookie, self.csrf = port, None, None

    def call(self, method, path, body=None, headers=None, host=None, raw=None, csrf=True, json_type=True):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or f"127.0.0.1:{self.port}", **(headers or {})}
        if self.cookie:
            h["Cookie"] = self.cookie
        if csrf and self.csrf and method == "POST" and "X-CSRF" not in h:
            h["X-CSRF"] = self.csrf
        if method == "POST" and json_type:
            h.setdefault("Content-Type", "application/json")
        data = raw if raw is not None else (json.dumps(body) if body is not None else None)
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in h.items():
            c.putheader(k, v)
        if data is not None:
            c.putheader("Content-Length", str(len(data)))
        c.endheaders(data.encode() if isinstance(data, str) else data)
        r = c.getresponse()
        payload = r.read()
        c.close()
        for k, v in r.getheaders():
            if k.lower() == "set-cookie":
                pair = v.split(";")[0]
                self.cookie = None if pair.endswith("=") else pair
        try:
            return r.status, json.loads(payload), r
        except ValueError:
            return r.status, payload, r

    def signup(self, email="a@example.com", pw=PW):
        status, body, r = self.call("POST", "/api/auth/signup", {"email": email, "password": pw})
        assert status == 200, body
        _, me, _ = self.call("GET", "/api/me")
        self.csrf = me["csrf"]
        return r


@pytest.fixture
def app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    for name in ("landing", "auth", "app"):
        (static / f"{name}.html").write_text(f"<html>{name}</html>", encoding="utf-8")
    (static / "app.js").write_text("console.log(1)", encoding="utf-8")
    (static / "notes.txt").write_text("not an allowed type", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    monkeypatch.setattr(srv, "STATIC", static)
    ext = FakeExt({"rag chatbot": [cand("a/rag-chatbot", desc="A rag chatbot", stars=900)]})
    ext.last_status = None
    service = Service(tmp_path, ext=ext)
    accounts = Accounts(tmp_path / "users.db", Fernet.generate_key(), mailer=Mailer({}), limits={"find": 2, "analyze": 1})
    made = []

    def start(**kw):
        server = srv.make_server(service, accounts, "127.0.0.1", 0, **kw)
        srv.serve_in_thread(server)
        made.append(server)
        return server.server_address[1]
    start.accounts, start.service, start.tmp = accounts, service, tmp_path
    yield start
    for s in made:
        s.shutdown()
        s.server_close()


def wait_job(client, job, timeout=10):
    end = time.time() + timeout
    snap = {}
    while time.time() < end:
        _, snap, _ = client.call("GET", f"/api/jobs/{job}?since=0")
        if snap["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    return snap


def test_public_pages_and_the_app_gate_with_strict_headers(app):
    port = app()
    c = Client(port)
    status, body, r = c.call("GET", "/")
    assert status == 200 and b"landing" in body
    csp = r.getheader("Content-Security-Policy")
    assert "default-src 'none'" in csp and "script-src 'self'" in csp and "font-src 'self'" in csp
    assert r.getheader("X-Content-Type-Options") == "nosniff" and r.getheader("X-Frame-Options") == "DENY"
    assert r.getheader("Cache-Control") == "no-store" and r.getheader("Access-Control-Allow-Origin") is None
    for page in ("/login", "/signup", "/forgot", "/reset"):
        assert c.call("GET", page)[0] == 200
    status, _, r = c.call("GET", "/app")
    assert status == 302 and r.getheader("Location") == "/login"            # not logged in
    c.signup()
    assert c.call("GET", "/app")[0] == 200
    status, _, r = c.call("GET", "/login")
    assert status == 302 and r.getheader("Location") == "/app"              # already logged in


def test_the_session_cookie_is_httponly_samesite_strict_and_secure_over_https(app):
    r = Client(app()).signup()
    cookie = r.getheader("Set-Cookie")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Secure" not in cookie and r.getheader("Strict-Transport-Security") is None
    r2 = Client(app(secure_cookies=True)).signup("b@example.com")
    cookie2 = r2.getheader("Set-Cookie")
    assert cookie2.startswith("__Host-rl_session=") and "Secure" in cookie2 and "max-age" in r2.getheader("Strict-Transport-Security")


def test_a_wrong_host_header_is_refused_to_block_dns_rebinding(app):
    port = app()
    c = Client(port)
    for host in ("evil.example.com", f"evil.example.com:{port}", "127.0.0.1"):
        assert c.call("GET", "/", host=host)[0] == 403
        assert c.call("POST", "/api/auth/login", {"email": "a@example.com", "password": PW}, host=host)[0] == 403
    assert c.call("GET", "/", host=f"localhost:{port}")[0] == 200
    port2 = app(allowed_hosts={"repolens.example.com"})
    assert Client(port2).call("GET", "/", host="repolens.example.com")[0] == 200 and Client(port2).call("GET", "/")[0] == 403


def test_api_calls_need_a_login_and_never_reveal_keys(app):
    port = app()
    anon = Client(port)
    for path in ("/api/me", "/api/status", "/api/project", "/api/reports", "/api/mine/1", "/api/jobs/aaaaaaaaaaaa"):
        assert anon.call("GET", path)[0] == 401, path
    assert anon.call("POST", "/api/find", {"goal": "x"})[0] == 401
    c = Client(port)
    c.signup()
    status, me, _ = c.call("GET", "/api/me")
    assert status == 200 and me["user"] == {"email": "a@example.com", "verified": False} and me["csrf"]
    assert all(k["set"] is False for k in me["keys"])
    bogus = Client(port)
    bogus.cookie = "rl_session=not-a-real-session"
    assert bogus.call("GET", "/api/me")[0] == 401


def test_state_changing_calls_need_the_csrf_token_and_a_same_site_origin(app):
    port = app()
    c = Client(port)
    c.signup()
    good = {"goal": "rag chatbot", "language": "python", "top": 3}
    assert c.call("POST", "/api/find", good, csrf=False)[0] == 403
    assert c.call("POST", "/api/find", good, headers={"X-CSRF": "wrong"})[0] == 403
    assert c.call("POST", "/api/find", good, headers={"Origin": "https://evil.example.com"})[0] == 403
    assert c.call("POST", "/api/auth/login", {"email": "a@example.com", "password": PW}, headers={"Origin": "https://evil.example.com"})[0] == 403
    assert c.call("POST", "/api/find", good, headers={"Origin": f"http://127.0.0.1:{port}"})[0] == 202


def test_login_logout_and_generic_errors(app):
    port = app()
    Client(port).signup()
    c = Client(port)
    for body in ({"email": "a@example.com", "password": "wrong-password-1"}, {"email": "nobody@example.com", "password": PW}):
        status, out, _ = c.call("POST", "/api/auth/login", body)
        assert status == 401 and out == {"error": "Wrong email or password."}
    assert c.call("POST", "/api/auth/login", {"email": "a@example.com", "password": PW})[0] == 200
    _, me, _ = c.call("GET", "/api/me")
    c.csrf = me["csrf"]
    assert c.call("POST", "/api/auth/logout", {})[0] == 200
    assert c.cookie is None and c.call("GET", "/api/me")[0] == 401
    assert Client(port).call("POST", "/api/auth/signup", {"email": "a@example.com", "password": PW})[0] == 409
    assert Client(port).call("POST", "/api/auth/signup", {"email": "b@example.com", "password": "short"})[0] == 400


def test_static_files_are_served_only_from_the_static_folder_with_allowed_types(app):
    c = Client(app())
    assert c.call("GET", "/static/app.js")[0] == 200
    for bad in ("/static/notes.txt", "/static/../secret.txt", "/static/..%2fsecret.txt", "/static/%2e%2e/secret.txt", "/static/nope.js", "/static/"):
        status, body, _ = c.call("GET", bad)
        assert status == 404 and b"TOP SECRET" not in (body if isinstance(body, bytes) else json.dumps(body).encode()), bad
    assert c.call("GET", "/elsewhere")[0] == 404


def test_post_bodies_must_be_small_json(app):
    c = Client(app())
    c.signup()
    assert c.call("POST", "/api/find", raw='{"goal":"x"}', headers={"Content-Type": "text/plain"}, json_type=False)[0] == 415
    assert c.call("POST", "/api/find", raw="x" * 25_000)[0] == 413
    assert c.call("POST", "/api/find", raw="{not json")[0] == 400
    assert c.call("POST", "/api/find", raw="[1,2]")[0] == 400
    assert c.call("POST", "/api/find", {"goal": ""})[0] == 400
    assert c.call("POST", "/api/find", {"goal": "g" * 400})[0] == 400
    assert c.call("POST", "/api/nothing", {})[0] == 404


def test_find_runs_as_a_job_only_its_owner_can_poll_and_it_is_saved_to_their_history(app):
    port = app()
    a, b = Client(port), Client(port)
    a.signup("a@example.com")
    b.signup("b@example.com")
    status, body, _ = a.call("POST", "/api/find", {"goal": "rag chatbot", "language": "python", "top": 3})
    assert status == 202 and len(body["job"]) == 12
    assert b.call("GET", f"/api/jobs/{body['job']}")[0] == 404              # someone else's job looks like it does not exist
    snap = wait_job(a, body["job"])
    assert snap["status"] == "done", snap
    assert snap["result"]["ranked"][0]["full_name"] == "a/rag-chatbot" and snap["progress"][0].startswith("Turning your goal")
    mine = [r for r in a.call("GET", "/api/reports")[1] if r["group"] == "Your history"]
    assert len(mine) == 1 and mine[0]["label"] == "rag chatbot"
    saved = a.call("GET", f"/api/mine/{snap['result']['saved_id']}")
    assert saved[0] == 200 and saved[1]["result"]["ranked"]
    assert b.call("GET", f"/api/mine/{snap['result']['saved_id']}")[0] == 404 and not [r for r in b.call("GET", "/api/reports")[1] if r["group"] == "Your history"]
    assert a.call("GET", "/api/jobs/../../etc")[0] == 404


def test_one_job_at_a_time_and_daily_quotas_per_user(app):
    port = app()
    a, b = Client(port), Client(port)
    a.signup("a@example.com")
    b.signup("b@example.com")
    real = app.service.find

    def slow(*args, **kw):
        time.sleep(0.4)
        return real(*args, **kw)
    app.service.find = slow
    first = a.call("POST", "/api/find", {"goal": "rag chatbot"})
    assert first[0] == 202
    assert a.call("POST", "/api/find", {"goal": "rag chatbot"})[0] == 429          # already one running
    assert b.call("POST", "/api/find", {"goal": "rag chatbot"})[0] == 202           # another user is unaffected
    wait_job(a, first[1]["job"])
    second = a.call("POST", "/api/find", {"goal": "rag chatbot"})                   # second of the day (limit 2)
    assert second[0] == 202
    wait_job(a, second[1]["job"])
    status, body, _ = a.call("POST", "/api/find", {"goal": "rag chatbot"})
    assert status == 429 and "today's find limit" in body["error"]
    assert a.call("GET", "/api/me")[1]["usage"]["find"] == {"used": 2, "limit": 2}


def test_users_own_keys_are_saved_encrypted_used_for_their_jobs_and_never_sent_back(app):
    port = app()
    c = Client(port)
    c.signup()
    secret = "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    status, body, _ = c.call("POST", "/api/keys", {"provider": "groq", "key": secret})
    assert status == 200 and {"provider": "groq", "set": True, "last4": "3456"} in body["keys"] and secret not in json.dumps(body)
    assert secret not in json.dumps(c.call("GET", "/api/me")[1])
    assert secret.encode() not in (app.tmp / "users.db").read_bytes()
    assert c.call("POST", "/api/keys", {"provider": "evilcorp", "key": secret})[0] == 400
    seen = {}
    real = app.service.router_for

    def spy(keys):
        seen.update(keys or {})
        return None                                                              # facts-only for the test
    app.service.router_for = spy
    status, body, _ = c.call("POST", "/api/find", {"goal": "rag chatbot"})
    wait_job(c, body["job"])
    assert seen == {"groq": secret}
    app.service.router_for = real
    assert c.call("POST", "/api/keys/delete", {"provider": "groq"})[1]["keys"][0]["set"] is False


def test_analyze_refuses_local_paths_before_any_work_starts(app):
    c = Client(app())
    c.signup()
    for bad in ("C:/Users/me", "/etc/passwd", "../x", "", "a/b/c"):
        status, body, _ = c.call("POST", "/api/analyze", {"source": bad})
        assert status == 400 and "owner/name" in body["error"], bad
    assert c.call("GET", "/api/me")[1]["usage"]["analyze"]["used"] == 0              # refused requests cost nothing


def test_feedback_is_saved_per_user_and_report_paths_cannot_escape(app):
    c = Client(app())
    c.signup()
    status, body, _ = c.call("POST", "/api/feedback", {"kind": "find", "target": "a/b", "rating": "up", "goal": "g"})
    assert status == 200 and body == {"saved": True, "total": 1}
    assert c.call("POST", "/api/feedback", {"kind": "find", "target": "a/b", "rating": "great"})[0] == 400
    for bad in ("../secret.txt", "..%2fsecret.txt", "/etc/passwd", "x.json"):
        assert c.call("GET", f"/api/report?path={bad}")[0] == 400


def test_password_reset_and_email_verification_links_work_end_to_end(app):
    port = app()
    mail = app.accounts.mailer.outbox
    c = Client(port)
    c.signup()
    link = re.search(r"/verify\?token=([\w-]+)", mail[-1]["body"]).group(1)
    status, _, r = c.call("GET", f"/verify?token={link}")
    assert status == 302 and r.getheader("Location") == "/app?verified=1"
    assert c.call("GET", "/api/me")[1]["user"]["verified"] is True
    status, _, r = Client(port).call("GET", f"/verify?token={link}")                  # single use
    assert r.getheader("Location") == "/login?verified=0"
    anon = Client(port)
    assert anon.call("POST", "/api/auth/forgot", {"email": "nobody@example.com"})[0] == 200
    assert len(mail) == 1                                                             # no mail, same answer
    assert anon.call("POST", "/api/auth/forgot", {"email": "a@example.com"})[0] == 200
    tok = re.search(r"/reset\?token=([\w-]+)", mail[-1]["body"]).group(1)
    assert anon.call("POST", "/api/auth/reset", {"token": tok, "password": "a brand new passphrase"})[0] == 200
    assert anon.call("POST", "/api/auth/reset", {"token": tok, "password": "a brand new passphrase"})[0] == 400
    assert c.call("GET", "/api/me")[0] == 401                                         # the old session ended
    assert anon.call("POST", "/api/auth/login", {"email": "a@example.com", "password": "a brand new passphrase"})[0] == 200


def test_when_verification_is_required_unverified_users_cannot_start_jobs_or_save_keys(app):
    port = app(require_verified=True)
    c = Client(port)
    c.signup()
    assert c.call("POST", "/api/find", {"goal": "rag chatbot"})[0] == 403
    assert c.call("POST", "/api/keys", {"provider": "groq", "key": "gsk_ABCDEFGHIJKLMNOP"})[0] == 403
    assert c.call("POST", "/api/feedback", {"kind": "find", "target": "a/b", "rating": "up"})[0] == 200


def test_deleting_an_account_needs_the_password_and_ends_the_session(app):
    port = app()
    c = Client(port)
    c.signup()
    assert c.call("POST", "/api/auth/delete-account", {"password": "wrong-password-1"})[0] == 401
    assert c.call("POST", "/api/auth/delete-account", {"password": PW})[0] == 200
    assert c.call("GET", "/api/me")[0] == 401
    assert Client(port).call("POST", "/api/auth/login", {"email": "a@example.com", "password": PW})[0] == 401
