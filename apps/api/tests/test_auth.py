"""Sign-in, sessions, the ingest token, and who may open a report."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qa_dashboard import auth, storage, users
from qa_dashboard.main import create_app
from qa_dashboard.persistence.db import open_session
from tests.conftest import INGEST_TOKEN, TEST_USERNAME, add_user, make_settings, sign_in
from tests.test_playwright_parser import json_reporter_report

TOKEN_HEADER = {"Authorization": f"Bearer {INGEST_TOKEN}"}
WRONG_PASSWORD = "definitely not it"


def zipped(name: str, content: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


def push_report(
    client: TestClient,
    *,
    headers: dict[str, str] | None = None,
    bundle: bytes | None = None,
) -> Any:
    files: dict[str, Any] = {
        "report": ("report.json", json.dumps(json_reporter_report()), "application/json")
    }
    if bundle is not None:
        files["bundle"] = ("bundle.zip", bundle, "application/zip")
    return client.post(
        "/api/v1/ingest/playwright",
        files=files,
        headers=TOKEN_HEADER if headers is None else headers,
    )


# --- Passwords ----------------------------------------------------------------


def test_a_hash_verifies_only_its_own_password() -> None:
    stored = auth.hash_password("correct horse battery")
    assert auth.verify_password("correct horse battery", stored)
    assert not auth.verify_password("correct horse batterY", stored)


def test_the_same_password_hashes_differently_each_time() -> None:
    assert auth.hash_password("correct horse battery") != auth.hash_password(
        "correct horse battery"
    )


def test_the_stored_hash_does_not_contain_the_password() -> None:
    stored = auth.hash_password("correct horse battery")
    assert "correct horse battery" not in stored
    assert stored.startswith("scrypt$")


@pytest.mark.parametrize(
    "stored", ["", "plain-text", "scrypt$1$2$3$x", "bcrypt$a$b$c$d$e", "scrypt$x$8$1$aa$bb"]
)
def test_a_malformed_stored_hash_never_verifies(stored: str) -> None:
    assert not auth.verify_password("anything at all", stored)


def test_a_short_password_is_refused() -> None:
    with pytest.raises(auth.PasswordPolicyError, match="12"):
        auth.check_password_policy("short")


def test_the_username_is_not_accepted_as_the_password() -> None:
    with pytest.raises(auth.PasswordPolicyError):
        auth.check_password_policy("Alice.Wong.Dev", "alice.wong.dev")


# --- Session tokens -------------------------------------------------------------


def test_a_session_token_round_trips() -> None:
    token = auth.issue_session(7, 2, "secret", now=1_000)
    claims = auth.read_session(token, "secret", max_age_seconds=3600, now=1_010)
    assert claims == auth.SessionClaims(user_id=7, session_version=2, issued_at=1_000)


def test_an_expired_session_token_is_refused() -> None:
    token = auth.issue_session(7, 2, "secret", now=1_000)
    assert auth.read_session(token, "secret", max_age_seconds=3600, now=1_000 + 3601) is None


def test_a_token_signed_with_another_secret_is_refused() -> None:
    token = auth.issue_session(7, 2, "someone-else", now=1_000)
    assert auth.read_session(token, "secret", max_age_seconds=3600, now=1_001) is None


def test_an_edited_token_is_refused() -> None:
    token = auth.issue_session(7, 2, "secret", now=1_000)
    edited = "8" + token[1:]
    assert auth.read_session(edited, "secret", max_age_seconds=3600, now=1_001) is None


@pytest.mark.parametrize("token", [None, "", "a.b.c", "1.2.3.é", "x.y.z.w", "1.2.3.4.5"])
def test_garbage_tokens_are_refused(token: str | None) -> None:
    assert auth.read_session(token, "secret", max_age_seconds=3600) is None


# --- Throttle -----------------------------------------------------------------------


def test_the_throttle_locks_after_repeated_failures() -> None:
    throttle = auth.LoginThrottle(max_failures=3, window_seconds=60, lockout_seconds=120)
    for stamp in (0, 1, 2):
        throttle.record_failure("alice", now=stamp)
    assert throttle.seconds_locked("alice", now=3) == pytest.approx(119)
    assert throttle.seconds_locked("alice", now=125) == 0


def test_old_failures_fall_out_of_the_window() -> None:
    throttle = auth.LoginThrottle(max_failures=3, window_seconds=60, lockout_seconds=120)
    throttle.record_failure("alice", now=0)
    throttle.record_failure("alice", now=1)
    throttle.record_failure("alice", now=100)
    assert throttle.seconds_locked("alice", now=101) == 0


def test_clearing_forgets_failures() -> None:
    throttle = auth.LoginThrottle(max_failures=2, window_seconds=60, lockout_seconds=120)
    throttle.record_failure("alice", now=0)
    throttle.clear("alice")
    throttle.record_failure("alice", now=1)
    assert throttle.seconds_locked("alice", now=2) == 0


# --- Signing in over HTTP ------------------------------------------------------------


def test_signing_in_sets_a_protected_session_cookie(anon_client: TestClient) -> None:
    add_user()
    response = sign_in(anon_client)
    assert response.status_code == 200
    assert response.json() == {"username": TEST_USERNAME}
    cookie = response.headers["set-cookie"].lower()
    assert f"{auth.SESSION_COOKIE}=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_a_wrong_password_gets_a_generic_message(anon_client: TestClient) -> None:
    add_user()
    response = sign_in(anon_client, password=WRONG_PASSWORD)
    assert response.status_code == 401
    assert response.json()["detail"] == "Username or password is incorrect."


def test_an_unknown_username_gets_the_same_message(anon_client: TestClient) -> None:
    response = sign_in(anon_client, username="nobody")
    assert response.status_code == 401
    assert response.json()["detail"] == "Username or password is incorrect."


def test_usernames_are_not_case_sensitive(anon_client: TestClient) -> None:
    add_user()
    assert sign_in(anon_client, username=TEST_USERNAME.upper()).status_code == 200


def test_a_disabled_account_gets_the_same_message(anon_client: TestClient) -> None:
    add_user()
    with open_session() as db:
        users.set_disabled(db, TEST_USERNAME, True)
    response = sign_in(anon_client)
    assert response.status_code == 401
    assert response.json()["detail"] == "Username or password is incorrect."


def test_repeated_failures_lock_the_account(anon_client: TestClient) -> None:
    add_user()
    for _ in range(5):
        assert sign_in(anon_client, password=WRONG_PASSWORD).status_code == 401
    locked = sign_in(anon_client)
    assert locked.status_code == 429
    assert "Try again in" in locked.json()["detail"]


def test_a_successful_sign_in_resets_the_failure_count(anon_client: TestClient) -> None:
    add_user()
    for _ in range(4):
        sign_in(anon_client, password=WRONG_PASSWORD)
    assert sign_in(anon_client).status_code == 200
    for _ in range(4):
        assert sign_in(anon_client, password=WRONG_PASSWORD).status_code == 401


# --- Sessions guard what people read -------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/session",
        "/api/v1/filters",
        "/api/v1/execution",
        "/api/v1/defects",
        "/api/v1/ai",
        "/api/v1/runs/anything",
    ],
)
def test_dashboard_data_needs_a_session(anon_client: TestClient, path: str) -> None:
    assert anon_client.get(path).status_code == 401


def test_a_signed_in_user_reads_the_dashboard(anon_client: TestClient) -> None:
    add_user()
    sign_in(anon_client)
    assert anon_client.get("/api/v1/execution").status_code == 200
    assert anon_client.get("/api/v1/session").json() == {"username": TEST_USERNAME}


def test_signing_out_ends_the_session(anon_client: TestClient) -> None:
    add_user()
    sign_in(anon_client)
    assert anon_client.delete("/api/v1/session").status_code == 204
    assert anon_client.get("/api/v1/session").status_code == 401


def test_a_forged_cookie_is_refused(anon_client: TestClient) -> None:
    add_user()
    anon_client.cookies.set(auth.SESSION_COOKIE, auth.issue_session(1, 0, "not-the-server-secret"))
    assert anon_client.get("/api/v1/session").status_code == 401


def test_a_password_change_ends_existing_sessions(anon_client: TestClient) -> None:
    add_user()
    sign_in(anon_client)
    with open_session() as db:
        users.set_password(db, TEST_USERNAME, "an entirely new password")
    assert anon_client.get("/api/v1/session").status_code == 401
    assert sign_in(anon_client, password="an entirely new password").status_code == 200


def test_disabling_an_account_ends_its_session(anon_client: TestClient) -> None:
    add_user()
    sign_in(anon_client)
    with open_session() as db:
        users.set_disabled(db, TEST_USERNAME, True)
    assert anon_client.get("/api/v1/session").status_code == 401


def test_health_needs_no_session(anon_client: TestClient) -> None:
    assert anon_client.get("/health").status_code == 200


# --- The ingest token ------------------------------------------------------------------


def test_pushing_needs_the_ingest_token(anon_client: TestClient) -> None:
    response = push_report(anon_client, headers={})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_wrong_ingest_token_is_refused(anon_client: TestClient) -> None:
    assert push_report(anon_client, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_a_browser_session_alone_cannot_push(anon_client: TestClient) -> None:
    """A browser attaches cookies to cross-site requests; it never attaches a bearer token."""
    add_user()
    sign_in(anon_client)
    assert push_report(anon_client, headers={}).status_code == 401


def test_the_right_ingest_token_can_push(anon_client: TestClient) -> None:
    assert push_report(anon_client).status_code == 200


@pytest.mark.parametrize(
    "path", ["/api/v1/ingest/playwright", "/api/v1/ingest/jira", "/api/v1/ingest/agent-runs"]
)
def test_every_ingest_route_is_guarded(anon_client: TestClient, path: str) -> None:
    assert anon_client.post(path).status_code == 401


def test_pushing_is_closed_when_no_token_is_configured(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, ingest_token=""))) as closed:
        response = push_report(closed, headers={"Authorization": "Bearer "})
    assert response.status_code == 503
    assert "QA_INGEST_TOKEN" in response.json()["detail"]


# --- Reports ------------------------------------------------------------------------------


def test_a_report_needs_a_session(anon_client: TestClient) -> None:
    run_id = push_report(anon_client, bundle=zipped("index.html", "<html>report</html>")).json()[
        "run_id"
    ]
    assert anon_client.get(f"/reports/{run_id}/index.html").status_code == 401


def test_a_signed_in_user_opens_a_report(anon_client: TestClient) -> None:
    run_id = push_report(anon_client, bundle=zipped("index.html", "<html>report</html>")).json()[
        "run_id"
    ]
    add_user()
    sign_in(anon_client)
    response = anon_client.get(f"/reports/{run_id}/index.html")
    assert response.status_code == 200
    assert response.text == "<html>report</html>"


def test_a_folder_url_serves_its_index(anon_client: TestClient) -> None:
    bundle = zipped("playwright-html/index.html", "<html>nested</html>")
    run_id = push_report(anon_client, bundle=bundle).json()["run_id"]
    add_user()
    sign_in(anon_client)
    assert anon_client.get(f"/reports/{run_id}/playwright-html/").text == "<html>nested</html>"


def test_report_paths_cannot_leave_the_run_folder(anon_client: TestClient, tmp_path: Path) -> None:
    run_id = push_report(anon_client, bundle=zipped("index.html", "<html>ok</html>")).json()[
        "run_id"
    ]
    (tmp_path / "storage" / "secret.txt").write_text("do not serve", encoding="utf-8")

    assert storage.resolve_report_file("..", "secret.txt") is None
    assert storage.resolve_report_file(".", "secret.txt") is None
    assert storage.resolve_report_file(run_id, "../../secret.txt") is None
    assert storage.resolve_report_file(run_id, "index.html") is not None

    add_user()
    sign_in(anon_client)
    for url in (f"/reports/{run_id}/..%2F..%2Fsecret.txt", "/reports/%2E%2E/secret.txt"):
        response = anon_client.get(url)
        assert response.status_code == 404
        assert "do not serve" not in response.text
