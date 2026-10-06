"""Create .env on first run and fill in any empty generated secret.

An existing value is never changed, and no secret is ever printed.

    python3 scripts/ensure_env.py
"""

from __future__ import annotations

import secrets
import stat
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"
EXAMPLE_FILE = REPO_ROOT / ".env.example"

GENERATED: dict[str, Callable[[], str]] = {
    "QA_SESSION_SECRET": lambda: secrets.token_urlsafe(48),
    "QA_INGEST_TOKEN": lambda: secrets.token_urlsafe(32),
}


def main() -> int:
    created = not ENV_FILE.exists()
    source = EXAMPLE_FILE if created else ENV_FILE
    lines = source.read_text(encoding="utf-8").splitlines()

    filled: list[str] = []
    for key, generate in GENERATED.items():
        index = next(
            (
                position
                for position, line in enumerate(lines)
                if not line.lstrip().startswith("#") and line.partition("=")[0].strip() == key
            ),
            None,
        )
        if index is None:
            lines.append(f"{key}={generate()}")
            filled.append(key)
        elif not lines[index].partition("=")[2].strip():
            lines[index] = f"{key}={generate()}"
            filled.append(key)

    if created or filled:
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ENV_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)

    if created:
        print("Created .env from .env.example.")
    for key in filled:
        print(f"Generated {key} in .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
