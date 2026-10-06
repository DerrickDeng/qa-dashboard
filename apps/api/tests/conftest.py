"""Fixtures: a fresh database and storage per test, and clients with and without credentials."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qa_dashboard import auth, users
from qa_dashboard.main import create_app
from qa_dashboard.persistence.db import open_session
from qa_dashboard.settings import Settings

INGEST_TOKEN = "test-ingest-token"
TEST_USERNAME = "tester"
TEST_PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def fast_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full-cost scrypt is the point in production and only slow in tests."""
    monkeypatch.setattr(auth, "SCRYPT_N", 2**10)


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": f"sqlite+pysqlite:///{tmp_path / 'qa.db'}",
        "storage_root": str(tmp_path / "storage"),
        "session_secret": "test-session-secret",
        "ingest_token": INGEST_TOKEN,
    }
    values.update(overrides)
    # _env_file=None keeps a developer's own .env out of the tests.
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def anon_client(tmp_path: Path) -> Iterator[TestClient]:
    """No session and no ingest token."""
    with TestClient(create_app(make_settings(tmp_path))) as test_client:
        yield test_client


def add_user(username: str = TEST_USERNAME, password: str = TEST_PASSWORD) -> None:
    with open_session() as db:
        users.create_user(db, username, password)


def sign_in(client: TestClient, username: str = TEST_USERNAME, password: str = TEST_PASSWORD):  # type: ignore[no-untyped-def]
    return client.post("/api/v1/session", json={"username": username, "password": password})


@pytest.fixture
def client(anon_client: TestClient) -> TestClient:
    """Signed in and carrying the ingest token, for tests about the data itself."""
    add_user()
    assert sign_in(anon_client).status_code == 200
    anon_client.headers["Authorization"] = f"Bearer {INGEST_TOKEN}"
    return anon_client
