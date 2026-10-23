"""User accounts for the hosted version of RepoLens (standard library plus `cryptography` for key storage).

What is stored and how:
- passwords: never stored; only a salted scrypt hash. Wrong logins and unknown emails take the same time and give the
  same message, and repeated failures are rate limited;
- sessions: a random token in an HttpOnly cookie; only its SHA-256 is stored, so a leaked database cannot be replayed;
- each user's own model API keys (bring-your-own-key): encrypted at rest with a server secret, never sent back to the
  page (it only learns "set, ends in ABCD"), and used only for that user's jobs;
- one-time tokens (email verification, password reset): random, stored hashed, expire, single use;
- per-user daily quotas, and each user's saved analyses and feedback.
Every message in an AuthError is safe to show to the user."""
from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

SESSION_DAYS = 14
TOKEN_HOURS = {"verify": 48, "reset": 1}
MIN_PASSWORD, MAX_PASSWORD = 10, 128
KEY_PROVIDERS = ("groq", "gemini", "openrouter")
DEFAULT_LIMITS = {"find": 20, "analyze": 10}
HISTORY_KEPT = 50
RATE_WINDOW = 15 * 60
RATE_PER_ACCOUNT, RATE_PER_IP = 8, 40
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s.]{2,}$")
_SCRYPT = dict(n=2 ** 15, r=8, p=1, maxmem=2 ** 26, dklen=32)

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(sid TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    csrf TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tokens(th TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS keys(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, provider TEXT NOT NULL,
    ct BLOB NOT NULL, last4 TEXT NOT NULL, PRIMARY KEY(user_id, provider));
CREATE TABLE IF NOT EXISTS usage(user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, day TEXT NOT NULL,
    kind TEXT NOT NULL, n INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, day, kind));
CREATE TABLE IF NOT EXISTS analyses(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, target TEXT NOT NULL, created REAL NOT NULL, result TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    ts REAL NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL, rating TEXT NOT NULL, goal TEXT, note TEXT);
"""


class AuthError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class Mailer:
    """Sends mail over SMTP when REPOLENS_SMTP_HOST is set. Otherwise (local development) it keeps the message in
    `outbox` and prints it, so you can click the link yourself."""

    def __init__(self, env=os.environ):
        self.host, self.port = env.get("REPOLENS_SMTP_HOST"), int(env.get("REPOLENS_SMTP_PORT") or 587)
        self.user, self.password = env.get("REPOLENS_SMTP_USER"), env.get("REPOLENS_SMTP_PASSWORD")
        self.sender = env.get("REPOLENS_MAIL_FROM") or self.user or "repolens@localhost"
        self.outbox: list[dict] = []

    @property
    def real(self) -> bool:
        return bool(self.host)

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.real:
            self.outbox.append({"to": to, "subject": subject, "body": body})
            del self.outbox[:-20]
            print(f"\n[dev mail, no SMTP configured] to {to}: {subject}\n{body}\n")
            return
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=20) as s:
            s.starttls()
            if self.user:
                s.login(self.user, self.password or "")
            s.send_message(msg)


def load_secret(path: Path, env=os.environ) -> bytes:
    """The key that encrypts users' API keys: REPOLENS_SECRET_KEY, else a file created on first run."""
    given = env.get("REPOLENS_SECRET_KEY")
    if given:
        return given.encode()
    if path.is_file():
        return path.read_bytes().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    path.write_bytes(key)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return key


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def _check_password(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), **_SCRYPT)
        return hmac.compare_digest(got, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


_DUMMY = _hash_password("not-a-real-password")          # compared against when the email is unknown, to equalize timing


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def normalize_email(email) -> str:
    e = (email or "").strip().lower() if isinstance(email, str) else ""
    if len(e) > 254 or not _EMAIL.match(e):
        raise AuthError("Enter a valid email address.")
    return e


def check_password_rules(password) -> str:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise AuthError(f"Use a password of at least {MIN_PASSWORD} characters.")
    if len(password) > MAX_PASSWORD:
        raise AuthError(f"Use a password of at most {MAX_PASSWORD} characters.")
    if password.lower() in {"password123", "1234567890", "qwertyuiop", "password12", "passwordpassword"}:
        raise AuthError("That password is too common. Pick another.")
    return password


class Accounts:
    def __init__(self, path: Path | str, secret: bytes, mailer: Mailer | None = None, base_url: str = "http://127.0.0.1:8765",
                 limits: dict | None = None, require_verified: bool = False, now=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fernet = Fernet(secret)
        self.mailer = mailer or Mailer()
        self.base_url = base_url.rstrip("/")
        self.limits = {**DEFAULT_LIMITS, **(limits or {})}
        self.require_verified = require_verified
        self.now = now
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        with self._db() as db:
            db.executescript(SCHEMA)

    @contextlib.contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        finally:
            db.close()

    # ------------------------------------------------------------------ rate limiting (in memory, per process)
    def _throttle(self, kind: str, *keys: str, limits: tuple[int, ...]) -> None:
        t = self.now()
        with self._lock:
            for key, cap in zip(keys, limits):
                k = f"{kind}:{key}"
                hits = [x for x in self._attempts.get(k, []) if t - x < RATE_WINDOW]
                self._attempts[k] = hits
                if len(hits) >= cap:
                    wait = int((RATE_WINDOW - (t - hits[0])) / 60) + 1
                    raise AuthError(f"Too many attempts. Wait about {wait} minute(s) and try again.", 429)

    def _hit(self, kind: str, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._attempts.setdefault(f"{kind}:{key}", []).append(self.now())

    # ------------------------------------------------------------------ sign up / log in
    def signup(self, email, password, ip: str = "-") -> dict:
        email, password = normalize_email(email), check_password_rules(password)
        self._throttle("signup", ip, limits=(10,))
        self._hit("signup", ip)
        pw = _hash_password(password)
        try:
            with self._db() as db:
                cur = db.execute("INSERT INTO users(email, pw, verified, created) VALUES(?,?,?,?)", (email, pw, 0, self.now()))
                uid = cur.lastrowid
        except sqlite3.IntegrityError:
            raise AuthError("An account with that email already exists. Try logging in.", 409) from None
        self._send_token(uid, email, "verify")
        return self.user(uid)

    def login(self, email, password, ip: str = "-") -> dict:
        email = normalize_email(email) if isinstance(email, str) else ""
        self._throttle("login", f"{ip}|{email}", ip, limits=(RATE_PER_ACCOUNT, RATE_PER_IP))
        with self._db() as db:
            row = db.execute("SELECT id, pw FROM users WHERE email=?", (email,)).fetchone()
        ok = _check_password(password if isinstance(password, str) else "", row["pw"] if row else _DUMMY) and row is not None
        if not ok:
            self._hit("login", f"{ip}|{email}", ip)
            raise AuthError("Wrong email or password.", 401)
        return self.user(row["id"])

    def user(self, uid: int) -> dict | None:
        with self._db() as db:
            r = db.execute("SELECT id, email, verified, created FROM users WHERE id=?", (uid,)).fetchone()
        return {"id": r["id"], "email": r["email"], "verified": bool(r["verified"]), "created": r["created"]} if r else None

    # ------------------------------------------------------------------ sessions
    def create_session(self, uid: int) -> tuple[str, str]:
        token, csrf, t = secrets.token_urlsafe(32), secrets.token_urlsafe(24), self.now()
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE expires<?", (t,))
            db.execute("INSERT INTO sessions(sid, user_id, csrf, created, expires) VALUES(?,?,?,?,?)",
                       (_sha(token), uid, csrf, t, t + SESSION_DAYS * 86400))
        return token, csrf

    def session(self, token: str | None) -> dict | None:
        """The logged-in user for a session cookie value (with the session's CSRF token), or None."""
        if not token or len(token) > 100:
            return None
        with self._db() as db:
            r = db.execute("SELECT s.csrf, u.id, u.email, u.verified FROM sessions s JOIN users u ON u.id=s.user_id "
                           "WHERE s.sid=? AND s.expires>?", (_sha(token), self.now())).fetchone()
        return {"id": r["id"], "email": r["email"], "verified": bool(r["verified"]), "csrf": r["csrf"]} if r else None

    def logout(self, token: str | None) -> None:
        if token:
            with self._db() as db:
                db.execute("DELETE FROM sessions WHERE sid=?", (_sha(token),))

    def _drop_sessions(self, uid: int, keep: str | None = None) -> None:
        with self._db() as db:
            db.execute("DELETE FROM sessions WHERE user_id=? AND sid<>?", (uid, _sha(keep) if keep else ""))

    # ------------------------------------------------------------------ email verification and password reset
    def _send_token(self, uid: int, email: str, purpose: str) -> None:
        token = secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("DELETE FROM tokens WHERE user_id=? AND purpose=?", (uid, purpose))
            db.execute("INSERT INTO tokens(th, user_id, purpose, expires) VALUES(?,?,?,?)",
                       (_sha(token), uid, purpose, self.now() + TOKEN_HOURS[purpose] * 3600))
        if purpose == "verify":
            self.mailer.send(email, "Confirm your RepoLens email", f"Welcome to RepoLens.\n\nConfirm your email:\n{self.base_url}/verify?token={token}\n\nIf this was not you, ignore this message.")
        else:
            self.mailer.send(email, "Reset your RepoLens password", f"Choose a new password (link valid for one hour):\n{self.base_url}/reset?token={token}\n\nIf you did not ask for this, ignore this message.")

    def _use_token(self, token, purpose: str) -> int | None:
        if not isinstance(token, str) or len(token) > 100:
            return None
        with self._db() as db:
            r = db.execute("SELECT user_id FROM tokens WHERE th=? AND purpose=? AND expires>?", (_sha(token), purpose, self.now())).fetchone()
            if r:
                db.execute("DELETE FROM tokens WHERE th=?", (_sha(token),))
        return r["user_id"] if r else None

    def resend_verification(self, uid: int) -> None:
        u = self.user(uid)
        if u and not u["verified"]:
            self._throttle("resend", str(uid), limits=(3,))
            self._hit("resend", str(uid))
            self._send_token(uid, u["email"], "verify")

    def verify_email(self, token) -> bool:
        uid = self._use_token(token, "verify")
        if uid is None:
            return False
        with self._db() as db:
            db.execute("UPDATE users SET verified=1 WHERE id=?", (uid,))
        return True

    def forgot(self, email, ip: str = "-") -> None:
        """Always looks the same from outside, whether or not the email has an account."""
        self._throttle("forgot", ip, limits=(10,))
        self._hit("forgot", ip)
        try:
            email = normalize_email(email)
        except AuthError:
            return
        with self._db() as db:
            r = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if r:
            self._send_token(r["id"], email, "reset")

    def reset_password(self, token, new_password) -> None:
        check_password_rules(new_password)
        uid = self._use_token(token, "reset")
        if uid is None:
            raise AuthError("That reset link is invalid or has expired. Ask for a new one.")
        with self._db() as db:
            db.execute("UPDATE users SET pw=?, verified=1 WHERE id=?", (_hash_password(new_password), uid))
        self._drop_sessions(uid)

    def change_password(self, uid: int, old, new, keep_token: str | None) -> None:
        check_password_rules(new)
        with self._db() as db:
            r = db.execute("SELECT pw FROM users WHERE id=?", (uid,)).fetchone()
        if not r or not _check_password(old if isinstance(old, str) else "", r["pw"]):
            raise AuthError("Your current password is wrong.", 401)
        with self._db() as db:
            db.execute("UPDATE users SET pw=? WHERE id=?", (_hash_password(new), uid))
        self._drop_sessions(uid, keep=keep_token)

    def delete_account(self, uid: int, password) -> None:
        with self._db() as db:
            r = db.execute("SELECT pw FROM users WHERE id=?", (uid,)).fetchone()
        if not r or not _check_password(password if isinstance(password, str) else "", r["pw"]):
            raise AuthError("Password is wrong.", 401)
        with self._db() as db:
            db.execute("DELETE FROM users WHERE id=?", (uid,))            # cascades: sessions, keys, usage, history, feedback

    # ------------------------------------------------------------------ the user's own API keys
    def set_key(self, uid: int, provider, key) -> None:
        if provider not in KEY_PROVIDERS:
            raise AuthError("Unknown provider.")
        key = key.strip() if isinstance(key, str) else ""
        if not 8 <= len(key) <= 300 or not re.fullmatch(r"[A-Za-z0-9._\-]+", key):
            raise AuthError("That does not look like an API key (letters, digits, dots, dashes and underscores only).")
        with self._db() as db:
            db.execute("INSERT INTO keys(user_id, provider, ct, last4) VALUES(?,?,?,?) ON CONFLICT(user_id, provider) "
                       "DO UPDATE SET ct=excluded.ct, last4=excluded.last4", (uid, provider, self.fernet.encrypt(key.encode()), key[-4:]))

    def delete_key(self, uid: int, provider) -> None:
        with self._db() as db:
            db.execute("DELETE FROM keys WHERE user_id=? AND provider=?", (uid, provider))

    def list_keys(self, uid: int) -> list[dict]:
        """What the page may know: which providers are set and the last four characters. Never the key."""
        with self._db() as db:
            have = {r["provider"]: r["last4"] for r in db.execute("SELECT provider, last4 FROM keys WHERE user_id=?", (uid,))}
        return [{"provider": p, "set": p in have, "last4": have.get(p)} for p in KEY_PROVIDERS]

    def keys_for_jobs(self, uid: int) -> dict[str, str]:
        out = {}
        with self._db() as db:
            for r in db.execute("SELECT provider, ct FROM keys WHERE user_id=?", (uid,)):
                with contextlib.suppress(InvalidToken):
                    out[r["provider"]] = self.fernet.decrypt(bytes(r["ct"])).decode()
        return out

    # ------------------------------------------------------------------ quotas, history, feedback
    def _day(self) -> str:
        return datetime.fromtimestamp(self.now(), timezone.utc).strftime("%Y-%m-%d")

    def usage(self, uid: int) -> dict:
        with self._db() as db:
            used = {r["kind"]: r["n"] for r in db.execute("SELECT kind, n FROM usage WHERE user_id=? AND day=?", (uid, self._day()))}
        return {k: {"used": used.get(k, 0), "limit": lim} for k, lim in self.limits.items()}

    def count_use(self, uid: int, kind: str) -> None:
        """Count one use against today's limit, or refuse."""
        lim = self.limits.get(kind)
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO usage(user_id, day, kind, n) VALUES(?,?,?,0)", (uid, self._day(), kind))
            n = db.execute("SELECT n FROM usage WHERE user_id=? AND day=? AND kind=?", (uid, self._day(), kind)).fetchone()["n"]
            if lim is not None and n >= lim:
                raise AuthError(f"You have used today's {kind} limit ({lim}). It resets at midnight UTC.", 429)
            db.execute("UPDATE usage SET n=n+1 WHERE user_id=? AND day=? AND kind=?", (uid, self._day(), kind))

    def save_result(self, uid: int, kind: str, target: str, result: dict) -> int:
        with self._db() as db:
            cur = db.execute("INSERT INTO analyses(user_id, kind, target, created, result) VALUES(?,?,?,?,?)",
                             (uid, kind, target[:200], self.now(), json.dumps(result, ensure_ascii=False)))
            db.execute("DELETE FROM analyses WHERE user_id=? AND id NOT IN (SELECT id FROM analyses WHERE user_id=? ORDER BY id DESC LIMIT ?)",
                       (uid, uid, HISTORY_KEPT))
            return cur.lastrowid

    def history(self, uid: int) -> list[dict]:
        with self._db() as db:
            return [{"id": r["id"], "kind": r["kind"], "target": r["target"], "created": r["created"]}
                    for r in db.execute("SELECT id, kind, target, created FROM analyses WHERE user_id=? ORDER BY id DESC", (uid,))]

    def get_result(self, uid: int, rid) -> dict | None:
        with self._db() as db:
            r = db.execute("SELECT kind, target, result FROM analyses WHERE user_id=? AND id=?", (uid, rid)).fetchone()
        return {"kind": r["kind"], "target": r["target"], "result": json.loads(r["result"])} if r else None

    def add_feedback(self, uid: int, kind: str, target: str, rating: str, goal: str = "", note: str = "") -> int:
        with self._db() as db:
            db.execute("INSERT INTO feedback(user_id, ts, kind, target, rating, goal, note) VALUES(?,?,?,?,?,?,?)",
                       (uid, self.now(), kind, target, rating, goal, note))
            return db.execute("SELECT COUNT(*) c FROM feedback WHERE user_id=?", (uid,)).fetchone()["c"]
