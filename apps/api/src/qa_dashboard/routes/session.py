"""Sign in, check who is signed in, and sign out."""

from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from .. import users
from ..auth import SESSION_COOKIE, LoginThrottle, issue_session
from .dependencies import AppSettings, CurrentUser, DbSession

router = APIRouter(prefix="/api/v1", tags=["session"])

#: One message for every failure, so a reply never says which accounts exist.
INCORRECT_CREDENTIALS = "Username or password is incorrect."


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class SessionUser(BaseModel):
    username: str


@router.post("/session", response_model=SessionUser, summary="Sign in")
def sign_in(
    payload: LoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
    settings: AppSettings,
) -> SessionUser:
    throttle: LoginThrottle = request.app.state.login_throttle
    key = payload.username.strip().lower()

    wait = throttle.seconds_locked(key)
    if wait > 0:
        minutes = max(1, math.ceil(wait / 60))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Too many failed sign-in attempts. "
                f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
            ),
        )

    user = users.authenticate(session, payload.username, payload.password)
    if user is None:
        throttle.record_failure(key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INCORRECT_CREDENTIALS)

    throttle.clear(key)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=issue_session(user.id, user.session_version, request.app.state.session_secret),
        max_age=settings.session_max_age_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )
    return SessionUser(username=user.username)


@router.get("/session", response_model=SessionUser, summary="The signed-in account")
def signed_in_user(user: CurrentUser) -> SessionUser:
    return SessionUser(username=user.username)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
def sign_out(response: Response, settings: AppSettings) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
    )
