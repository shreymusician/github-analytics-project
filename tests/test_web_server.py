import http.client
import json
import time

import pytest

from repolens.web import server as srv
from repolens.web.service import Service
from tests.test_discover import FakeExt, cand  # noqa: F401

TOKEN = "tok-123_secret"


@pytest.fixture
def app(tmp_path, monkeypatch):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<html><meta name='t' content='__TOKEN__'></html>", encoding="utf-8")
    (static / "app.js").write_text("console.log(1)", encoding="utf-8")
    (static / "notes.txt").write_text("not an allowed type", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOP SECRET", encoding="utf-8")
    monkeypatch.setattr(srv, "STATIC", static)
    ext = FakeExt({"rag chatbot": [cand("a/rag-chatbot", desc="A rag chatbot", stars=900)]})
    ext.last_status = None
    service = Service(tmp_path, ext=ext, router=None, env_keys={"groq": "gsk_SECRETSECRETSECRETSECRET"})
    server = srv.make_server(service, "127.0.0.1", 0, TOKEN)
    srv.serve_in_thread(server)
    yield server.server_address[1], tmp_path
    server.shutdown()
    server.server_close()


def call(port, method, path, body=None, headers=None, host=None, raw=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": host or f"127.0.0.1:{port}", **(headers or {})}
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
    try:
        return r.status, json.loads(payload), r
    except ValueError:
        return r.status, payload, r


API = {"X-Token": TOKEN}
JSON = {"X-Token": TOKEN, "Content-Type": "application/json"}


def test_the_page_needs_the_secret_token_and_has_strict_headers(app):
    port, _ = app
    assert call(port, "GET", "/")[0] == 403 and call(port, "GET", "/?t=wrong")[0] == 403
    status, body, r = call(port, "GET", f"/?t={TOKEN}")
    assert status == 200 and TOKEN.encode() in body and b"__TOKEN__" not in body
    assert "default-src 'none'" in r.getheader("Content-Security-Policy") and "script-src 'self'" in r.getheader("Content-Security-Policy")
    assert r.getheader("X-Content-Type-Options") == "nosniff" and r.getheader("X-Frame-Options") == "DENY"
    assert r.getheader("Cache-Control") == "no-store" and r.getheader("Access-Control-Allow-Origin") is None      # never CORS


def test_a_wrong_host_header_is_refused_to_block_dns_rebinding(app):
    port, _ = app
    for host in ("evil.example.com", "evil.example.com:80", f"evil.example.com:{port}", "127.0.0.1"):
        assert call(port, "GET", f"/?t={TOKEN}", host=host)[0] == 403
        assert call(port, "GET", "/api/status", headers=API, host=host)[0] == 403
    assert call(port, "GET", "/api/status", headers=API, host=f"localhost:{port}")[0] == 200


def test_api_calls_need_the_token_and_never_reveal_keys(app):
    port, _ = app
    for path in ("/api/status", "/api/project", "/api/reports"):
        assert call(port, "GET", path)[0] == 403 and call(port, "GET", path, headers={"X-Token": "nope"})[0] == 403
    status, body, _ = call(port, "GET", "/api/status", headers=API)
    assert status == 200 and body["can_narrate"] is True
    assert "SECRET" not in json.dumps(body)
    assert call(port, "POST", "/api/feedback", {"kind": "find", "target": "a/b", "rating": "up"}, headers={"Content-Type": "application/json"})[0] == 403


def test_static_files_are_served_only_from_the_static_folder_with_allowed_types(app):
    port, _ = app
    assert call(port, "GET", "/static/app.js")[0] == 200
    for bad in ("/static/notes.txt", "/static/../secret.txt", "/static/..%2fsecret.txt", "/static/%2e%2e/secret.txt", "/static/nope.js", "/static/"):
        status, body, _ = call(port, "GET", bad)
        assert status == 404 and b"TOP SECRET" not in (body if isinstance(body, bytes) else json.dumps(body).encode()), bad
    assert call(port, "GET", "/elsewhere")[0] == 404


def test_post_bodies_must_be_small_json(app):
    port, _ = app
    assert call(port, "POST", "/api/find", raw='{"goal":"x"}', headers={"X-Token": TOKEN, "Content-Type": "text/plain"})[0] == 415
    assert call(port, "POST", "/api/find", raw="x" * 25_000, headers=JSON)[0] == 413
    assert call(port, "POST", "/api/find", raw="{not json", headers=JSON)[0] == 400
    assert call(port, "POST", "/api/find", raw="[1,2]", headers=JSON)[0] == 400
    assert call(port, "POST", "/api/find", {"goal": ""}, headers=JSON)[0] == 400
    assert call(port, "POST", "/api/find", {"goal": "g" * 400}, headers=JSON)[0] == 400
    assert call(port, "POST", "/api/nothing", {}, headers=JSON)[0] == 404


def test_find_runs_as_a_job_the_page_can_poll(app):
    port, _ = app
    status, body, _ = call(port, "POST", "/api/find", {"goal": "rag chatbot", "language": "python", "top": 3}, headers=JSON)
    assert status == 202 and len(body["job"]) == 12
    end = time.time() + 10
    snap = {}
    while time.time() < end:
        _, snap, _ = call(port, "GET", f"/api/jobs/{body['job']}?since=0", headers=API)
        if snap["status"] in ("done", "error"):
            break
        time.sleep(0.05)
    assert snap["status"] == "done", snap
    assert snap["result"]["ranked"][0]["full_name"] == "a/rag-chatbot" and snap["progress"][0].startswith("Turning your goal")
    assert call(port, "GET", f"/api/jobs/{body['job']}?since={snap['next']}", headers=API)[1]["progress"] == []      # nothing new to report
    assert call(port, "GET", "/api/jobs/aaaaaaaaaaaa", headers=API)[0] == 404
    assert call(port, "GET", "/api/jobs/../../etc", headers=API)[0] == 404


def test_analyze_refuses_local_paths_before_any_work_starts(app):
    port, _ = app
    for bad in ("C:/Users/me", "/etc/passwd", "../x", "", "a/b/c"):
        status, body, _ = call(port, "POST", "/api/analyze", {"source": bad}, headers=JSON)
        assert status == 400 and "owner/name" in body["error"], bad


def test_feedback_is_saved_and_report_paths_cannot_escape(app):
    port, tmp = app
    status, body, _ = call(port, "POST", "/api/feedback", {"kind": "find", "target": "a/b", "rating": "up", "goal": "g"}, headers=JSON)
    assert status == 200 and body["saved"] is True and (tmp / "data/feedback/feedback.jsonl").is_file()
    assert call(port, "POST", "/api/feedback", {"kind": "find", "target": "a/b", "rating": "great"}, headers=JSON)[0] == 400
    for bad in ("../secret.txt", "..%2fsecret.txt", "/etc/passwd", "x.json"):
        assert call(port, "GET", f"/api/report?path={bad}", headers=API)[0] == 400
