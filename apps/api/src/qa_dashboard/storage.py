"""Where uploaded HTML report bundles are unpacked and served from.

The root is configured at startup rather than being a fixed constant, so a test
run writes into its own directory instead of the real one.
"""

from __future__ import annotations

import io
import re
import secrets
import shutil
import zipfile
from pathlib import Path

DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parents[4] / "storage"

#: Guards against a zip bomb or a path-traversal entry in an uploaded bundle.
MAX_BUNDLE_BYTES = 300 * 1024 * 1024
MAX_BUNDLE_ENTRIES = 20_000

_root: Path = DEFAULT_STORAGE_ROOT


class BundleError(ValueError):
    """The uploaded report bundle could not be stored safely."""


def configure(root: Path | str | None = None) -> Path:
    global _root
    _root = Path(root) if root else DEFAULT_STORAGE_ROOT
    reports_root().mkdir(parents=True, exist_ok=True)
    return _root


def reports_root() -> Path:
    return _root / "reports"


def report_dir(run_id: str) -> Path:
    return reports_root() / run_id


def store_bundle(run_id: str, blob: bytes) -> Path:
    """Validate a zipped Playwright HTML report, then unpack it for serving.

    Every entry is checked before anything is written, and a re-upload replaces
    the previous bundle rather than being skipped - otherwise a second push of
    the same run would keep a stale report, and would never be validated.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as error:
        raise BundleError("The report bundle is not a valid zip file.") from error

    target = report_dir(run_id)
    resolved_target = target.resolve()

    entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    if len(entries) > MAX_BUNDLE_ENTRIES:
        raise BundleError("The report bundle contains too many files.")
    if sum(entry.file_size for entry in entries) > MAX_BUNDLE_BYTES:
        raise BundleError("The report bundle is too large once unpacked.")

    # Check every path before writing any of them.
    for entry in entries:
        destination = (resolved_target / entry.filename).resolve()
        if not destination.is_relative_to(resolved_target):
            raise BundleError(f"The bundle contains an unsafe path: {entry.filename!r}")

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        destination = (resolved_target / entry.filename).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(entry) as source, destination.open("wb") as handle:
            shutil.copyfileobj(source, handle)

    return target


def bundle_entry_point(run_id: str) -> str | None:
    """Relative URL of the report's index.html, allowing for a wrapping folder."""
    base = report_dir(run_id)
    if not base.exists():
        return None
    if (base / "index.html").exists():
        return f"/reports/{run_id}/index.html"
    for candidate in sorted(base.glob("*/index.html")):
        return f"/reports/{run_id}/{candidate.parent.name}/index.html"
    return None


#: A run id as the ingest endpoint produces it. Starting with a letter or digit rules
#: out "." and "..".
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def resolve_report_file(run_id: str, file_path: str) -> Path | None:
    """The file to serve for a report URL, or None when it is missing or would
    fall outside that run's folder. The storage root also holds the session
    secret, so nothing above a run folder may ever be reachable."""
    if not _RUN_ID.match(run_id):
        return None
    root = reports_root().resolve()
    base = (root / run_id).resolve()
    if base.parent != root or not base.is_dir():
        return None
    target = (base / file_path).resolve() if file_path else base
    if not target.is_relative_to(base):
        return None
    if target.is_dir():
        target = target / "index.html"
    return target if target.is_file() else None


def load_or_create_session_secret() -> str:
    """A session-signing secret kept in storage, created on first use.

    Used only when QA_SESSION_SECRET is not set, so a local run needs no setup and
    sessions still survive a restart.
    """
    path = _root / "session_secret"
    if path.is_file():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    _root.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_urlsafe(48)
    path.write_text(secret, encoding="utf-8")
    path.chmod(0o600)
    return secret
