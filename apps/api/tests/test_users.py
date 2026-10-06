"""Accounts: the service rules, and the command-line tool built on them."""

from __future__ import annotations

import importlib.util
import io
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy.orm import Session

from qa_dashboard import auth, users
from qa_dashboard.persistence.db import configure_engine
from qa_dashboard.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[3]
PASSWORD = "correct horse battery"


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    engine = configure_engine(
        Settings(_env_file=None, database_url=f"sqlite+pysqlite:///{tmp_path / 'users.db'}")  # type: ignore[call-arg]
    )
    with Session(engine) as session:
        yield session


def test_usernames_are_stored_lowercase(db: Session) -> None:
    assert users.create_user(db, "  Alice.Wong ", PASSWORD).username == "alice.wong"


def test_the_password_is_stored_only_as_a_hash(db: Session) -> None:
    user = users.create_user(db, "alice", PASSWORD)
    assert PASSWORD not in user.password_hash
    assert user.password_hash.startswith("scrypt$")


def test_a_taken_username_is_refused_whatever_its_case(db: Session) -> None:
    users.create_user(db, "alice", PASSWORD)
    with pytest.raises(users.UserError, match="already taken"):
        users.create_user(db, "ALICE", PASSWORD)


@pytest.mark.parametrize("name", ["", "   ", ".hidden", "has space", "semi;colon", "x" * 65])
def test_invalid_usernames_are_refused(db: Session, name: str) -> None:
    with pytest.raises(users.UserError):
        users.create_user(db, name, PASSWORD)


def test_an_email_address_works_as_a_username(db: Session) -> None:
    assert (
        users.create_user(db, "derrick@example.test", PASSWORD).username == "derrick@example.test"
    )


def test_a_short_password_is_refused(db: Session) -> None:
    with pytest.raises(auth.PasswordPolicyError):
        users.create_user(db, "alice", "short")


def test_valid_credentials_authenticate_and_record_the_sign_in(db: Session) -> None:
    users.create_user(db, "alice", PASSWORD)
    user = users.authenticate(db, "ALICE", PASSWORD)
    assert user is not None
    assert user.last_login_at is not None


def test_a_wrong_password_does_not_authenticate(db: Session) -> None:
    users.create_user(db, "alice", PASSWORD)
    assert users.authenticate(db, "alice", "not the password at all") is None


def test_an_unknown_user_does_not_authenticate(db: Session) -> None:
    assert users.authenticate(db, "ghost", PASSWORD) is None


def test_a_malformed_username_does_not_authenticate(db: Session) -> None:
    assert users.authenticate(db, "no spaces allowed", PASSWORD) is None


def test_a_disabled_account_does_not_authenticate_even_with_the_right_password(db: Session) -> None:
    users.create_user(db, "alice", PASSWORD)
    users.set_disabled(db, "alice", True)
    assert users.authenticate(db, "alice", PASSWORD) is None


def test_changing_the_password_moves_the_session_version(db: Session) -> None:
    user = users.create_user(db, "alice", PASSWORD)
    before = user.session_version
    users.set_password(db, "alice", "another long password")
    assert user.session_version == before + 1
    assert users.authenticate(db, "alice", PASSWORD) is None
    assert users.authenticate(db, "alice", "another long password") is not None


def test_disabling_moves_the_session_version_and_enabling_restores_sign_in(db: Session) -> None:
    user = users.create_user(db, "alice", PASSWORD)
    users.set_disabled(db, "alice", True)
    assert user.session_version == 1
    users.set_disabled(db, "alice", False)
    assert users.authenticate(db, "alice", PASSWORD) is not None


def test_changing_an_unknown_account_is_refused(db: Session) -> None:
    with pytest.raises(users.UserError, match="No account"):
        users.set_password(db, "ghost", PASSWORD)


# --- The command-line tool --------------------------------------------------------------


def load_cli() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "manage_users", REPO_ROOT / "scripts" / "manage_users.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli_db(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"


def test_the_cli_creates_and_lists_an_account(
    cli_db: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = load_cli()
    monkeypatch.setattr(sys, "stdin", io.StringIO(PASSWORD + "\n"))
    assert cli.main(["--database-url", cli_db, "add", "Alice", "--password-stdin"]) == 0
    assert cli.main(["--database-url", cli_db, "list"]) == 0
    output = capsys.readouterr().out
    assert "alice" in output
    assert "active" in output
    assert PASSWORD not in output


def test_the_cli_refuses_a_short_password(
    cli_db: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = load_cli()
    monkeypatch.setattr(sys, "stdin", io.StringIO("short\n"))
    assert cli.main(["--database-url", cli_db, "add", "alice", "--password-stdin"]) == 1
    assert "12" in capsys.readouterr().err


def test_has_users_answers_with_its_exit_code(cli_db: str, monkeypatch: pytest.MonkeyPatch) -> None:
    cli = load_cli()
    assert cli.main(["--database-url", cli_db, "has-users"]) == 1
    monkeypatch.setattr(sys, "stdin", io.StringIO(PASSWORD + "\n"))
    cli.main(["--database-url", cli_db, "add", "alice", "--password-stdin"])
    assert cli.main(["--database-url", cli_db, "has-users"]) == 0


def test_the_cli_disables_and_enables(
    cli_db: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = load_cli()
    monkeypatch.setattr(sys, "stdin", io.StringIO(PASSWORD + "\n"))
    cli.main(["--database-url", cli_db, "add", "alice", "--password-stdin"])
    assert cli.main(["--database-url", cli_db, "disable", "alice"]) == 0
    cli.main(["--database-url", cli_db, "list"])
    assert "disabled" in capsys.readouterr().out
    assert cli.main(["--database-url", cli_db, "enable", "alice"]) == 0


def test_the_cli_reports_an_unknown_account(
    cli_db: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cli = load_cli()
    assert cli.main(["--database-url", cli_db, "disable", "ghost"]) == 1
    assert "No account" in capsys.readouterr().err
