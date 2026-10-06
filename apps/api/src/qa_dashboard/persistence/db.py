"""Engine and session wiring."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..settings import Settings
from .tables import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def configure_engine(settings: Settings) -> Engine:
    global _engine, _session_factory

    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    _engine = create_engine(settings.database_url, connect_args=connect_args, future=True)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    Base.metadata.create_all(_engine)
    return _engine


def session_scope() -> Iterator[Session]:
    if _session_factory is None:
        raise RuntimeError("The database engine has not been configured.")
    session = _session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def open_session() -> Iterator[Session]:
    yield from session_scope()
