"""Manage dashboard accounts from the command line.

    make user-add NAME=alice              prompts for the password twice
    make user-list
    make user-reset-password NAME=alice   also signs that account out everywhere
    make user-disable NAME=alice          also ends its sessions
    make user-enable NAME=alice

Passwords are never taken as command-line arguments, so they stay out of shell
history and process lists. For automation, --password-stdin reads one line.

Run from apps/api so it uses that Python environment:

    cd apps/api && uv run python ../../scripts/manage_users.py list
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))

from qa_dashboard import users  # noqa: E402
from qa_dashboard.auth import MIN_PASSWORD_LENGTH  # noqa: E402
from qa_dashboard.persistence.db import configure_engine, open_session  # noqa: E402
from qa_dashboard.settings import Settings  # noqa: E402

DASHBOARD_URL = "http://127.0.0.1:5174"


def read_new_password(from_stdin: bool) -> str:
    if from_stdin:
        return sys.stdin.readline().rstrip("\r\n")
    first = getpass.getpass(f"New password ({MIN_PASSWORD_LENGTH}+ characters): ")
    second = getpass.getpass("Repeat the password: ")
    if first != second:
        raise users.UserError("The two passwords do not match.")
    return first


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage QA dashboard accounts.")
    parser.add_argument("--database-url", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="create an account")
    add.add_argument("name")
    add.add_argument("--password-stdin", action="store_true", help="read the password from stdin")

    commands.add_parser("list", help="list accounts")

    reset = commands.add_parser("reset-password", help="set a new password")
    reset.add_argument("name")
    reset.add_argument("--password-stdin", action="store_true", help="read the password from stdin")

    commands.add_parser("disable", help="disable an account").add_argument("name")
    commands.add_parser("enable", help="re-enable an account").add_argument("name")
    commands.add_parser("has-users", help="exit 0 when at least one account exists")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings(database_url=args.database_url) if args.database_url else Settings()
    configure_engine(settings)

    try:
        if args.command == "add":
            password = read_new_password(args.password_stdin)
            with open_session() as db:
                name = users.create_user(db, args.name, password).username
            print(f"Created {name}. Sign in at {DASHBOARD_URL}")

        elif args.command == "list":
            with open_session() as db:
                rows = [
                    (
                        user.username,
                        "disabled" if user.disabled else "active",
                        f"{user.created_at:%Y-%m-%d %H:%M}",
                        f"{user.last_login_at:%Y-%m-%d %H:%M}" if user.last_login_at else "never",
                    )
                    for user in users.list_users(db)
                ]
            if not rows:
                print("No accounts yet. Create one: make user-add NAME=<name>")
            else:
                print(f"{'USERNAME':<28} {'STATUS':<9} {'CREATED':<17} LAST SIGN-IN")
                for username, state, created, last in rows:
                    print(f"{username:<28} {state:<9} {created:<17} {last}")

        elif args.command == "reset-password":
            password = read_new_password(args.password_stdin)
            with open_session() as db:
                name = users.set_password(db, args.name, password).username
            print(f"Password changed for {name}. Its existing sessions have ended.")

        elif args.command == "disable":
            with open_session() as db:
                name = users.set_disabled(db, args.name, True).username
            print(f"Disabled {name}. Its existing sessions have ended.")

        elif args.command == "enable":
            with open_session() as db:
                name = users.set_disabled(db, args.name, False).username
            print(f"Enabled {name}.")

        elif args.command == "has-users":
            with open_session() as db:
                return 0 if users.list_users(db) else 1

    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
