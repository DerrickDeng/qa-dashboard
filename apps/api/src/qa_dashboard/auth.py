"""Password hashing, session tokens, the ingest token check, and sign-in throttling.

Passwords use scrypt from the standard library with a random salt per password,
stored as ``scrypt$<n>$<r>$<p>$<salt>$<hash>`` so the cost can be raised later
without breaking hashes already stored.

A session is a signed cookie, ``<user id>.<session version>.<issued at>.<signature>``.
It is checked against the user row on every request: disabling an account or
changing its password bumps the session version, which ends every session issued
before the change.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass
from functools import cache

SESSION_COOKIE = "qa_session"

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 1024

#: scrypt cost. Read at call time, so tests can lower it without touching this file.
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
_KEY_LENGTH = 32
_MAX_MEMORY = 64 * 1024 * 1024


class PasswordPolicyError(ValueError):
    """The password does not meet the policy."""


def check_password_policy(password: str, username: str = "") -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Use at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Use at most {MAX_PASSWORD_LENGTH} characters.")
    if username and password.strip().lower() == username.strip().lower():
        raise PasswordPolicyError("The password must not be the username.")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P, _KEY_LENGTH)
    return "$".join(
        ["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P), _encode(salt), _encode(digest)]
    )


def verify_password(password: str, stored: str) -> bool:
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt, expected = _decode(parts[4]), _decode(parts[5])
        candidate = _scrypt(password, salt, n, r, p, len(expected))
    except ValueError:
        return False
    return hmac.compare_digest(candidate, expected)


@cache
def dummy_password_hash() -> str:
    """Checked against when a username is unknown, so the reply takes as long as a real check."""
    return hash_password(secrets.token_urlsafe(24))


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAX_MEMORY, dklen=length
    )


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- Sessions -----------------------------------------------------------------


@dataclass(frozen=True)
class SessionClaims:
    user_id: int
    session_version: int
    issued_at: int


def issue_session(
    user_id: int, session_version: int, secret: str, *, now: float | None = None
) -> str:
    issued = int(time.time() if now is None else now)
    payload = f"{user_id}.{session_version}.{issued}"
    return f"{payload}.{_sign(payload, secret)}"


def read_session(
    token: str | None,
    secret: str,
    *,
    max_age_seconds: int,
    now: float | None = None,
) -> SessionClaims | None:
    """The claims in a valid, unexpired token, else None."""
    if not token or not secret:
        return None
    parts = token.split(".")
    if len(parts) != 4:
        return None
    payload = ".".join(parts[:3])
    # Compared as bytes: a tampered cookie may hold non-ASCII text.
    if not hmac.compare_digest(parts[3].encode("utf-8"), _sign(payload, secret).encode("utf-8")):
        return None
    try:
        user_id, version, issued = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    current = time.time() if now is None else now
    if issued > current + 60 or current - issued > max_age_seconds:
        return None
    return SessionClaims(user_id=user_id, session_version=version, issued_at=issued)


def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


# --- Ingest token --------------------------------------------------------------


def token_matches(presented: str | None, expected: str) -> bool:
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented.encode("utf-8"), expected.encode("utf-8"))


# --- Throttling ----------------------------------------------------------------


class LoginThrottle:
    """Locks a username for a while after repeated failed sign-ins.

    Kept in memory, so a restart clears it. It is keyed on the username only: that
    slows password guessing against one account, at the cost that someone who
    knows a username can lock that account out until the lockout expires.
    """

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 900,
        lockout_seconds: float = 900,
        max_tracked: int = 10_000,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self.max_tracked = max_tracked
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}

    def seconds_locked(self, key: str, *, now: float | None = None) -> float:
        current = self._clock(now)
        until = self._locked_until.get(key, 0.0)
        if until <= current:
            self._locked_until.pop(key, None)
            return 0.0
        return until - current

    def record_failure(self, key: str, *, now: float | None = None) -> None:
        current = self._clock(now)
        if len(self._failures) >= self.max_tracked:
            self._prune(current)
        recent = [
            stamp for stamp in self._failures.get(key, []) if current - stamp < self.window_seconds
        ]
        recent.append(current)
        if len(recent) >= self.max_failures:
            self._locked_until[key] = current + self.lockout_seconds
            self._failures.pop(key, None)
        else:
            self._failures[key] = recent

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)
        self._locked_until.pop(key, None)

    def _prune(self, current: float) -> None:
        self._failures = {
            key: stamps
            for key, stamps in self._failures.items()
            if any(current - stamp < self.window_seconds for stamp in stamps)
        }

    @staticmethod
    def _clock(now: float | None) -> float:
        return time.monotonic() if now is None else now
