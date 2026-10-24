"""Security tests for sign-up / log-in. Runs against a temporary copy of the DB.

    cd hw4/backend && .venv/bin/pytest -q
"""

import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REAL_DB = BACKEND.parent / "data" / "campus_customs.db"
ORIGIN = {"Origin": "http://localhost:5173"}
GOOD = {
    "first_name": "Grace",
    "last_name": "Hopper",
    "email": "Grace.Hopper@yale.edu",
    "password": "cobol-compiler-1952",
    "confirm_password": "cobol-compiler-1952",
}


@pytest.fixture()
def client(tmp_path):
    db_copy = tmp_path / "test.db"
    shutil.copy(REAL_DB, db_copy)
    os.environ["CAMPUS_DB_PATH"] = str(db_copy)
    sys.path.insert(0, str(BACKEND))
    # Re-import every backend module so all of them see this test's CAMPUS_DB_PATH copy.
    for name, mod in list(sys.modules.items()):
        if getattr(mod, "__file__", None) and Path(mod.__file__).parent == BACKEND:  # main, agent, tools, memory, …
            sys.modules.pop(name, None)
    import main
    from fastapi.testclient import TestClient

    with TestClient(main.app, headers=ORIGIN) as c:
        c.db_path = db_copy
        yield c


def query(client, sql, *args):
    with sqlite3.connect(client.db_path) as conn:
        return conn.execute(sql, args).fetchall()


def test_signup_sets_secure_session_and_hides_secrets(client):
    r = client.post("/api/auth/signup", json=GOOD)
    assert r.status_code == 201
    assert r.json() == {"first_name": "Grace", "last_name": "Hopper", "email": "grace.hopper@yale.edu"}

    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie

    assert client.get("/api/auth/me").json()["first_name"] == "Grace"


def test_password_is_hashed_never_stored_plain(client):
    client.post("/api/auth/signup", json=GOOD)
    (stored,) = query(client, "SELECT password_hash FROM users WHERE email = ?", "grace.hopper@yale.edu")[0]
    assert GOOD["password"] not in stored
    algo, salt, digest = stored.split("$")
    assert algo == "pbkdf2_sha256" and len(salt) == 16 and len(digest) == 64
    # Same settings as the seed data: PBKDF2-HMAC-SHA256, 120k iterations, UTF-8 salt.
    import hashlib
    assert hashlib.pbkdf2_hmac("sha256", GOOD["password"].encode(), salt.encode(), 120_000).hex() == digest


def test_seeded_test_user_can_log_in(client):
    r = client.post("/api/auth/login", json={"email": "test@campuscustoms.yale.edu", "password": "password"})
    assert r.status_code == 200 and r.json()["first_name"] == "Test"
    assert client.get("/api/auth/me").json()["email"] == "test@campuscustoms.yale.edu"


def test_login_does_not_rewrite_stored_hash(client):
    before = query(client, "SELECT password_hash FROM users WHERE email = ?", "test@campuscustoms.yale.edu")
    client.post("/api/auth/login", json={"email": "test@campuscustoms.yale.edu", "password": "password"})
    after = query(client, "SELECT password_hash FROM users WHERE email = ?", "test@campuscustoms.yale.edu")
    assert before == after


def test_new_account_logs_in_after_signup(client):
    client.post("/api/auth/signup", json=GOOD)
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": GOOD["email"], "password": GOOD["password"]})
    assert r.status_code == 200


def test_session_token_is_hashed_in_db(client):
    r = client.post("/api/auth/signup", json=GOOD)
    token = r.cookies.get("cc_session")
    stored = [row[0] for row in query(
        client, "SELECT token_hash FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.email = ?", "grace.hopper@yale.edu"
    )]
    assert token and len(stored) == 1 and token not in stored


@pytest.mark.parametrize(
    "change, message",
    [
        ({"confirm_password": "something-else-99"}, "do not match"),
        ({"password": "short1", "confirm_password": "short1"}, "at least"),
        ({"password": "password123", "confirm_password": "password123"}, "easy to guess"),
        ({"password": "grace.hopper-pw", "confirm_password": "grace.hopper-pw"}, "email"),
        ({"email": "not-an-email"}, "valid email"),
        ({"first_name": "<script>"}, "special characters"),
    ],
)
def test_signup_validation(client, change, message):
    r = client.post("/api/auth/signup", json={**GOOD, **change})
    assert r.status_code == 422
    assert message in r.json()["detail"]


def test_validation_errors_never_echo_password(client):
    r = client.post("/api/auth/signup", json={**GOOD, "first_name": "", "password": "secret-value-xyz"})
    assert r.status_code == 422
    assert "secret-value-xyz" not in r.text


def test_cannot_inject_extra_fields(client):
    r = client.post("/api/auth/signup", json={**GOOD, "id": 1, "password_hash": "x"})
    assert r.status_code == 422


def test_duplicate_email_case_insensitive(client):
    client.post("/api/auth/signup", json=GOOD)
    r = client.post("/api/auth/signup", json={**GOOD, "email": "GRACE.HOPPER@YALE.EDU"})
    assert r.status_code == 409


def test_login_logout_flow(client):
    client.post("/api/auth/signup", json=GOOD)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401

    r = client.post("/api/auth/login", json={"email": "grace.hopper@yale.edu", "password": GOOD["password"]})
    assert r.status_code == 200 and r.json()["first_name"] == "Grace"
    old_token = r.cookies.get("cc_session")

    client.post("/api/auth/logout")
    client.cookies.set("cc_session", old_token, path="/api")
    assert client.get("/api/auth/me").status_code == 401  # token revoked server-side


def test_login_errors_are_generic(client):
    client.post("/api/auth/signup", json=GOOD)
    wrong_pw = client.post("/api/auth/login", json={"email": GOOD["email"], "password": "nope-nope-nope"})
    no_user = client.post("/api/auth/login", json={"email": "nobody@yale.edu", "password": "nope-nope-nope"})
    assert wrong_pw.status_code == no_user.status_code == 401
    assert wrong_pw.json() == no_user.json() == {"detail": "Invalid email or password."}


def test_login_rate_limited(client):
    bad = {"email": "target@yale.edu", "password": "guess-guess-1"}
    codes = [client.post("/api/auth/login", json=bad).status_code for _ in range(6)]
    assert codes[:5] == [401] * 5 and codes[5] == 429


def test_sql_injection_is_harmless(client):
    before = query(client, "SELECT count(*) FROM users")[0][0]
    r = client.post("/api/auth/login", json={"email": "' OR 1=1 --", "password": "' OR '1'='1"})
    assert r.status_code == 401
    assert query(client, "SELECT count(*) FROM users")[0][0] == before


def test_cross_site_posts_blocked(client):
    for headers in ({"Origin": "https://evil.example"}, {"Origin": ""}):
        r = client.post("/api/auth/login", json={"email": "a@b.co", "password": "x"}, headers=headers)
        assert r.status_code == 403


def test_api_sends_security_headers(client):
    r = client.get("/api/products")
    assert r.status_code == 200 and len(r.json()) == 102
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"
