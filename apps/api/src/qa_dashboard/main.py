"""QA dashboard API.

Three data sources, all pushed in rather than polled:

  * Playwright reports  - CI or `make push-report` posts them after a run
  * JIRA issues         - the sync job in scripts/sync_jira.py
  * Agent run logs      - written by the generation agents after review

People sign in with a local account. Pushes carry a bearer token instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import storage
from .auth import LoginThrottle
from .persistence.db import configure_engine
from .routes import dashboard, ingest, reports, session
from .settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    storage.configure(resolved.storage_root or None)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        configure_engine(resolved)
        yield

    app = FastAPI(
        title="QA Dashboard API",
        version="0.1.0",
        description=__doc__,
        lifespan=lifespan,
    )

    # With no QA_SESSION_SECRET, a secret is generated once and kept in storage, so
    # sessions survive a restart and no secret is ever committed.
    app.state.session_secret = resolved.session_secret or storage.load_or_create_session_secret()
    app.state.login_throttle = LoginThrottle()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(session.router)
    app.include_router(ingest.router)
    app.include_router(dashboard.router)
    app.include_router(reports.router)

    # Open on purpose: the start script polls it before anyone can sign in.
    @app.get("/health", tags=["health"])
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "jira_live": resolved.jira_live_enabled,
            "ingest_enabled": bool(resolved.ingest_token),
        }

    app.dependency_overrides[get_settings] = lambda: resolved
    return app


app = create_app()
