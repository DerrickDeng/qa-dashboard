"""Shared dependencies: the database session, settings, the filter slice, the JIRA
mapping, and the two ways a caller proves who it is.

* People use the dashboard with a session cookie (`current_user`).
* Scripts and CI push data with a bearer token (`require_ingest_token`).

The ingest routes deliberately accept only the token, never the cookie. A browser
attaches cookies to requests that other sites make to this origin, so a push
endpoint that trusted the cookie could be triggered from another page. A bearer
token is never sent automatically, so it cannot.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..auth import SESSION_COOKIE, read_session, token_matches
from ..ingest.jira import FieldMapping
from ..metrics.filters import Slice
from ..persistence.db import session_scope
from ..persistence.tables import User
from ..settings import Settings, get_settings

DbSession = Annotated[Session, Depends(session_scope)]
AppSettings = Annotated[Settings, Depends(get_settings)]

MAPPING_PATH = (
    Path(__file__).resolve().parents[4].parent / "samples" / "jira" / "field-mapping.json"
)


def current_slice(
    days: Annotated[int, Query(ge=1, le=180, description="Window length in days")] = 14,
    application_code: Annotated[str | None, Query()] = None,
    region: Annotated[str | None, Query()] = None,
    environment: Annotated[str | None, Query()] = None,
) -> Slice:
    return Slice(
        days=days,
        application_code=application_code or None,
        region=region or None,
        environment=environment or None,
    )


def jira_mapping() -> FieldMapping:
    return FieldMapping.load(MAPPING_PATH if MAPPING_PATH.exists() else None)


def current_user(request: Request, session: DbSession, settings: AppSettings) -> User:
    """The signed-in account, or 401.

    The cookie's signature and age are checked first, then the account itself: a
    disabled account, or one whose password changed after the cookie was issued,
    no longer counts as signed in.
    """
    claims = read_session(
        request.cookies.get(SESSION_COOKIE),
        request.app.state.session_secret,
        max_age_seconds=settings.session_max_age_hours * 3600,
    )
    user = session.get(User, claims.user_id) if claims else None
    if (
        claims is None
        or user is None
        or user.disabled
        or user.session_version != claims.session_version
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in to continue.")
    return user


def require_ingest_token(request: Request, settings: AppSettings) -> None:
    """Pass only a request that carries the configured bearer token."""
    if not settings.ingest_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pushing data is turned off until QA_INGEST_TOKEN is set. Run: make setup",
        )
    scheme, _, presented = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token_matches(presented.strip(), settings.ingest_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid ingest token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )


CurrentSlice = Annotated[Slice, Depends(current_slice)]
JiraMapping = Annotated[FieldMapping, Depends(jira_mapping)]
CurrentUser = Annotated[User, Depends(current_user)]
