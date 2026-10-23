import re
import sqlite3

import pytest
from cryptography.fernet import Fernet

from repolens.web.accounts import Accounts, AuthError, Mailer, load_secret

PW = "correct horse battery"


class Clock:
    def __init__(self):
        self.t = 1_700_000_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def acc(tmp_path):
    clock = Clock()
    a = Accounts(tmp_path / "users.db", Fernet.generate_key(), mailer=Mailer({}), limits={"find": 2, "analyze": 1}, now=clock)
    a.clock = clock
    return a


def token_from_mail(acc, which):
    return re.search(rf"{which}\?token=([\w-]+)", acc.mailer.outbox[-1]["body"]).group(1)


def test_signup_then_login_and_the_password_is_stored_only_as_a_hash(acc, tmp_path):
    u = acc.signup("  Me@Example.com ", PW)
    assert u["email"] == "me@example.com" and u["verified"] is False
    assert acc.login("me@example.com", PW)["id"] == u["id"]
    raw = sqlite3.connect(tmp_path / "users.db").execute("SELECT pw FROM users").fetchone()[0]
    assert PW not in raw and raw.startswith("scrypt$")


def test_bad_input_and_duplicates_are_refused_with_safe_messages(acc):
    for bad in ("", "nope", "a@b", "x" * 300 + "@a.com", None, 5):
        with pytest.raises(AuthError):
            acc.signup(bad, PW)
    for bad in ("short", "x" * 200, "password123", None):
        with pytest.raises(AuthError):
            acc.signup("a@example.com", bad)
    acc.signup("a@example.com", PW)
    with pytest.raises(AuthError) as e:
        acc.signup("A@example.com", PW)
    assert e.value.status == 409


def test_wrong_password_and_unknown_email_give_the_same_answer(acc):
    acc.signup("a@example.com", PW)
    msgs = set()
    for email, pw in (("a@example.com", "wrong-password-1"), ("nobody@example.com", PW), ("a@example.com", None)):
        with pytest.raises(AuthError) as e:
            acc.login(email, pw)
        msgs.add((str(e.value), e.value.status))
    assert msgs == {("Wrong email or password.", 401)}


def test_repeated_failures_are_rate_limited_and_recover(acc):
    acc.signup("a@example.com", PW)
    for _ in range(8):
        with pytest.raises(AuthError):
            acc.login("a@example.com", "wrong-password-1", ip="1.1.1.1")
    with pytest.raises(AuthError) as e:
        acc.login("a@example.com", PW, ip="1.1.1.1")                 # even the right password is refused for now
    assert e.value.status == 429
    acc.clock.t += 16 * 60
    assert acc.login("a@example.com", PW, ip="1.1.1.1")["email"] == "a@example.com"


def test_sessions_store_only_a_hash_expire_and_end_on_logout(acc, tmp_path):
    uid = acc.signup("a@example.com", PW)["id"]
    token, csrf = acc.create_session(uid)
    assert acc.session(token)["email"] == "a@example.com" and acc.session(token)["csrf"] == csrf
    assert token not in str(sqlite3.connect(tmp_path / "users.db").execute("SELECT * FROM sessions").fetchall())
    assert acc.session("garbage") is None and acc.session(None) is None and acc.session("x" * 500) is None
    acc.logout(token)
    assert acc.session(token) is None
    t2, _ = acc.create_session(uid)
    acc.clock.t += 15 * 86400
    assert acc.session(t2) is None


def test_email_verification_is_single_use_and_expires(acc):
    uid = acc.signup("a@example.com", PW)["id"]
    tok = token_from_mail(acc, "verify")
    assert acc.verify_email("nope") is False
    assert acc.verify_email(tok) is True and acc.user(uid)["verified"] is True
    assert acc.verify_email(tok) is False
    acc.resend_verification(uid)                                     # already verified: nothing is sent
    uid2 = acc.signup("b@example.com", PW)["id"]
    tok2 = token_from_mail(acc, "verify")
    acc.clock.t += 49 * 3600
    assert acc.verify_email(tok2) is False and acc.user(uid2)["verified"] is False


def test_password_reset_works_once_ends_other_sessions_and_hides_whether_an_email_exists(acc):
    uid = acc.signup("a@example.com", PW)["id"]
    token, _ = acc.create_session(uid)
    sent = len(acc.mailer.outbox)
    acc.forgot("nobody@example.com")
    acc.forgot("not an email")
    assert len(acc.mailer.outbox) == sent                            # nothing sent, nothing revealed
    acc.forgot("a@example.com")
    tok = token_from_mail(acc, "reset")
    with pytest.raises(AuthError):
        acc.reset_password(tok, "short")
    acc.reset_password(tok, "a brand new passphrase")
    assert acc.session(token) is None
    assert acc.login("a@example.com", "a brand new passphrase")["id"] == uid
    with pytest.raises(AuthError):
        acc.reset_password(tok, "another passphrase here")           # used already


def test_change_password_needs_the_old_one_and_keeps_only_this_session(acc):
    uid = acc.signup("a@example.com", PW)["id"]
    keep, _ = acc.create_session(uid)
    other, _ = acc.create_session(uid)
    with pytest.raises(AuthError):
        acc.change_password(uid, "wrong-old-password", "a brand new passphrase", keep)
    acc.change_password(uid, PW, "a brand new passphrase", keep)
    assert acc.session(keep) and acc.session(other) is None


def test_api_keys_are_encrypted_never_listed_in_full_and_private_to_their_owner(acc, tmp_path):
    a, b = acc.signup("a@example.com", PW)["id"], acc.signup("b@example.com", PW)["id"]
    secret = "gsk_ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    acc.set_key(a, "groq", secret)
    assert secret.encode() not in (tmp_path / "users.db").read_bytes()
    listing = acc.list_keys(a)
    assert {"provider": "groq", "set": True, "last4": "3456"} in listing and secret not in str(listing)
    assert acc.keys_for_jobs(a) == {"groq": secret} and acc.keys_for_jobs(b) == {}
    for bad in ("short", "has space in it 12345", "x" * 400, None):
        with pytest.raises(AuthError):
            acc.set_key(a, "groq", bad)
    with pytest.raises(AuthError):
        acc.set_key(a, "evilcorp", secret)
    acc.delete_key(a, "groq")
    assert acc.keys_for_jobs(a) == {}


def test_a_different_server_secret_cannot_read_stored_keys(tmp_path):
    a1 = Accounts(tmp_path / "u.db", Fernet.generate_key(), mailer=Mailer({}))
    uid = a1.signup("a@example.com", PW)["id"]
    a1.set_key(uid, "groq", "gsk_ABCDEFGHIJKLMNOP")
    a2 = Accounts(tmp_path / "u.db", Fernet.generate_key(), mailer=Mailer({}))
    assert a2.keys_for_jobs(uid) == {}


def test_daily_quotas_count_per_user_and_reset_each_day(acc):
    a, b = acc.signup("a@example.com", PW)["id"], acc.signup("b@example.com", PW)["id"]
    acc.count_use(a, "analyze")
    with pytest.raises(AuthError) as e:
        acc.count_use(a, "analyze")
    assert e.value.status == 429 and acc.usage(a)["analyze"] == {"used": 1, "limit": 1}
    acc.count_use(b, "analyze")                                       # someone else's budget is separate
    acc.clock.t += 86400
    acc.count_use(a, "analyze")


def test_history_is_private_capped_and_feedback_is_stored_per_user(acc):
    a, b = acc.signup("a@example.com", PW)["id"], acc.signup("b@example.com", PW)["id"]
    rid = acc.save_result(a, "analyze", "x/y", {"profile": {"repo": "x/y"}})
    assert acc.get_result(a, rid)["result"]["profile"]["repo"] == "x/y"
    assert acc.get_result(b, rid) is None and acc.history(b) == []
    for i in range(60):
        acc.save_result(a, "find", f"goal {i}", {})
    assert len(acc.history(a)) == 50
    assert acc.add_feedback(a, "find", "x/y", "up", "goal", "note") == 1


def test_deleting_an_account_removes_everything_it_owned(acc, tmp_path):
    uid = acc.signup("a@example.com", PW)["id"]
    acc.create_session(uid)
    acc.set_key(uid, "groq", "gsk_ABCDEFGHIJKLMNOP")
    acc.save_result(uid, "find", "g", {})
    acc.add_feedback(uid, "find", "x/y", "up")
    with pytest.raises(AuthError):
        acc.delete_account(uid, "wrong-password-1")
    acc.delete_account(uid, PW)
    db = sqlite3.connect(tmp_path / "users.db")
    for table in ("users", "sessions", "keys", "analyses", "feedback", "usage"):
        assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def test_the_server_secret_is_created_once_or_taken_from_the_environment(tmp_path):
    p = tmp_path / "secret.key"
    k1 = load_secret(p, {})
    assert load_secret(p, {}) == k1 and Fernet(k1)
    assert load_secret(p, {"REPOLENS_SECRET_KEY": "abc"}) == b"abc"
