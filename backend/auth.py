"""Accounts: sign-up, log-in, log-out and "who am I".

Security measures (see output/harness.md for the full list):
- Passwords hashed with PBKDF2-HMAC-SHA256 (120,000 iterations, random salt
  per user), the same scheme as the seeded accounts, and compared in constant
  time. Plain-text passwords are never stored or logged.
- Sessions are random 256-bit tokens in an HttpOnly, SameSite=Strict cookie,
  so page JavaScript (including injected scripts or a browsing AI agent) can't
  read them. The DB keeps only a SHA-256 of each token.
- Log-in errors are generic ("invalid email or password") and take the same
  time whether or not the email exists, so attackers can't probe for accounts.
- Failed log-ins and sign-ups are rate-limited per email and per IP.
- Request bodies reject unknown fields, so a client can't sneak in extra
  columns, and responses never include password hashes.
"""

import hashlib
import hmac
import os
import re
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

import db

SESSION_COOKIE = "cc_session"
SESSION_DAYS = 7
# Set COOKIE_SECURE=true when served over HTTPS so the cookie never travels in clear text.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

# One hashing scheme for sign-up AND log-in, matching the seeded users:
# PBKDF2-HMAC-SHA256, 120,000 iterations, stored as "pbkdf2_sha256$<salt>$<hex>".
# The salt is used as UTF-8 text. Changing any of these breaks every existing login.
HASH_PREFIX = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 120_000
SALT_HEX_CHARS = 16  # 8 random bytes as hex, same shape as the seeded salts

MIN_PASSWORD, MAX_PASSWORD = 10, 128
COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456789", "1234567890",
    "qwertyuiop", "iloveyale1", "yaleuniversity", "bulldogs123", "letmein123",
}
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")
NAME_RE = re.compile(r"^[^\x00-\x1f<>{}\[\]\\]{1,50}$")


# ---------- password hashing ----------

def _pbkdf2_hex(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS).hex()


def hash_password(password: str) -> str:
    """Sign-up: make a NEW random salt, hash, and store prefix$salt$hash."""
    salt = secrets.token_hex(SALT_HEX_CHARS // 2)
    return f"{HASH_PREFIX}${salt}${_pbkdf2_hex(password, salt)}"


def verify_password(password: str, stored: str) -> bool:
    """Log-in: never un-hash. Re-hash the typed password with the salt read out
    of the stored string (no new salt) and compare in constant time."""
    parts = stored.split("$")
    if len(parts) != 3 or parts[0] != HASH_PREFIX:
        return False
    _, salt, expected = parts
    return hmac.compare_digest(_pbkdf2_hex(password, salt), expected)


# Used when the email doesn't exist, so the response takes as long as a real check.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# ---------- rate limiting (in-memory; fine for one server process) ----------

class RateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit, self.window = limit, window_seconds
        self.hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        q, cutoff = self.hits[key], time.monotonic() - self.window
        while q and q[0] < cutoff:
            q.popleft()
        return q

    def blocked(self, key: str) -> int:
        """Seconds until `key` may try again, or 0 if allowed."""
        q = self._prune(key)
        return int(q[0] + self.window - time.monotonic()) + 1 if len(q) >= self.limit else 0

    def hit(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self, key: str) -> None:
        self.hits.pop(key, None)


login_failures_by_email = RateLimiter(limit=5, window_seconds=15 * 60)
login_failures_by_ip = RateLimiter(limit=20, window_seconds=15 * 60)
signups_by_ip = RateLimiter(limit=5, window_seconds=60 * 60)


def too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        status_code=429,
        detail="Too many attempts. Please wait a few minutes and try again.",
        headers={"Retry-After": str(retry_after)},
    )


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


# ---------- sessions ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def start_session(response: Response, user_id: int) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    with db.read_write() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < datetime('now')")
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, expires.strftime("%Y-%m-%d %H:%M:%S")),
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        path="/api",
    )


def end_session(response: Response, token: str | None) -> None:
    if token:
        with db.read_write() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    response.delete_cookie(SESSION_COOKIE, path="/api", samesite="strict", httponly=True, secure=COOKIE_SECURE)


# ---------- models ----------

class PublicUser(BaseModel):
    """The only user fields ever sent to the browser (no hash, no internal id)."""
    first_name: str
    last_name: str
    email: str


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    first_name: str = Field(min_length=1, max_length=50)
    last_name: str = Field(min_length=1, max_length=50)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD)
    confirm_password: str = Field(min_length=1, max_length=MAX_PASSWORD)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD)


def public_user(row) -> PublicUser:
    first = row["first_name"] or (row["name"] or "").split(" ")[0]
    last = row["last_name"] or " ".join((row["name"] or "").split(" ")[1:])
    return PublicUser(first_name=first, last_name=last, email=row["email"])


def password_problem(password: str, email: str, first: str, last: str) -> str | None:
    lowered = password.lower()
    if len(password) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters."
    if lowered in COMMON_PASSWORDS or len(set(password)) < 4:
        return "That password is too easy to guess. Try a longer phrase."
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in lowered:
        return "Password shouldn't contain your email address."
    if any(len(n) >= 3 and n.lower() in lowered for n in (first, last)):
        return "Password shouldn't contain your name."
    return None


# ---------- current user dependency (also for the chat agent later) ----------

def current_user(cc_session: str | None = Cookie(default=None)):
    """Returns the logged-in user's row, or None. Identity comes only from the
    session cookie, never from anything the client (or an AI) puts in a request body."""
    if not cc_session or len(cc_session) > 100:
        return None
    with db.read_only() as conn:
        return conn.execute(
            """
            SELECT u.id, u.name, u.first_name, u.last_name, u.email, u.created_at
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > datetime('now')
            """,
            (_token_hash(cc_session),),
        ).fetchone()


def require_user(user=Depends(current_user)):
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in.")
    return user


# ---------- routes ----------

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=PublicUser, status_code=201)
def signup(body: SignupRequest, request: Request, response: Response) -> PublicUser:
    ip = client_ip(request)
    if wait := signups_by_ip.blocked(ip):
        raise too_many(wait)

    email = body.email.lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(422, "Enter a valid email address.")
    if not (NAME_RE.match(body.first_name) and NAME_RE.match(body.last_name)):
        raise HTTPException(422, "Names can't contain special characters like < > { }.")
    if body.password != body.confirm_password:
        raise HTTPException(422, "Passwords do not match.")
    if problem := password_problem(body.password, email, body.first_name, body.last_name):
        raise HTTPException(422, problem)

    signups_by_ip.hit(ip)
    full_name = f"{body.first_name} {body.last_name}"
    try:
        with db.read_write() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, first_name, last_name, email, password_hash) VALUES (?, ?, ?, ?, ?)",
                (full_name, body.first_name, body.last_name, email, hash_password(body.password)),
            )
            user_id = cur.lastrowid
    except db.sqlite3.IntegrityError:
        raise HTTPException(409, "We couldn't create an account with that email. If you already have one, log in instead.")

    start_session(response, user_id)
    return PublicUser(first_name=body.first_name, last_name=body.last_name, email=email)


@router.post("/login", response_model=PublicUser)
def login(body: LoginRequest, request: Request, response: Response) -> PublicUser:
    ip, email = client_ip(request), body.email.strip().lower()
    if wait := max(login_failures_by_email.blocked(email), login_failures_by_ip.blocked(ip)):
        raise too_many(wait)

    with db.read_only() as conn:
        row = conn.execute(
            "SELECT id, name, first_name, last_name, email, password_hash FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    ok = verify_password(body.password, row["password_hash"] if row else _DUMMY_HASH) and row is not None
    if not ok:
        login_failures_by_email.hit(email)
        login_failures_by_ip.hit(ip)
        raise HTTPException(401, "Invalid email or password.")

    login_failures_by_email.reset(email)
    start_session(response, row["id"])
    return public_user(row)


@router.post("/logout", status_code=204)
def logout(response: Response, cc_session: str | None = Cookie(default=None)) -> None:
    end_session(response, cc_session)


@router.get("/me", response_model=PublicUser)
def me(user=Depends(require_user)) -> PublicUser:
    return public_user(user)
