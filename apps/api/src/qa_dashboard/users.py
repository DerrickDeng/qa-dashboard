"""Dashboard accounts: create them, change them, and check credentials."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import check_password_policy, dummy_password_hash, hash_password, verify_password
from .persistence.tables import User

USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._@-]{0,63}$")


class UserError(ValueError):
    """An account operation that cannot be done, with a message fit to show."""


def normalise_username(raw: str) -> str:
    username = raw.strip().lower()
    if not USERNAME_PATTERN.match(username):
        raise UserError(
            "Usernames are 1-64 characters of letters, digits, and . _ @ -, "
            "starting with a letter or digit."
        )
    return username


def find(session: Session, username: str) -> User | None:
    return session.scalar(select(User).where(User.username == username))


def create_user(session: Session, username: str, password: str) -> User:
    name = normalise_username(username)
    check_password_policy(password, name)
    if find(session, name) is not None:
        raise UserError(f"The username {name!r} is already taken.")
    now = _now()
    user = User(
        username=name,
        password_hash=hash_password(password),
        disabled=False,
        session_version=0,
        created_at=now,
        password_changed_at=now,
    )
    session.add(user)
    session.flush()
    return user


def set_password(session: Session, username: str, password: str) -> User:
    user = _require(session, username)
    check_password_policy(password, user.username)
    user.password_hash = hash_password(password)
    user.password_changed_at = _now()
    # Ends every session this account already has.
    user.session_version += 1
    session.flush()
    return user


def set_disabled(session: Session, username: str, disabled: bool) -> User:
    user = _require(session, username)
    if disabled and not user.disabled:
        user.session_version += 1
    user.disabled = disabled
    session.flush()
    return user


def list_users(session: Session) -> list[User]:
    return list(session.scalars(select(User).order_by(User.username)))


def authenticate(session: Session, username: str, password: str) -> User | None:
    """The account for valid credentials, else None.

    An unknown username, a wrong password, and a disabled account all return None,
    and an unknown username still runs a password check, so neither the reply nor
    its timing tells a caller which accounts exist.
    """
    try:
        name = normalise_username(username)
    except UserError:
        verify_password(password, dummy_password_hash())
        return None

    user = find(session, name)
    if user is None:
        verify_password(password, dummy_password_hash())
        return None
    if not verify_password(password, user.password_hash) or user.disabled:
        return None

    user.last_login_at = _now()
    return user


def _require(session: Session, username: str) -> User:
    user = find(session, normalise_username(username))
    if user is None:
        raise UserError(f"No account named {username.strip().lower()!r}.")
    return user


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
