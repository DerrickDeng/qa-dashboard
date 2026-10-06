"""Runtime settings, read from the environment and from the repository's .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QA_",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite+pysqlite:///{REPO_ROOT / 'qa_dashboard.db'}"
    #: Where uploaded report bundles are unpacked. Empty means repo-root/storage.
    storage_root: str = ""
    #: Comma-separated. Kept as text: pydantic-settings would otherwise expect JSON.
    cors_origins: str = "http://127.0.0.1:5174,http://localhost:5174"

    # --- Security ---------------------------------------------------------------
    #: Signs session cookies. Empty means a secret generated once and kept in storage.
    session_secret: str = ""
    session_max_age_hours: int = 12
    #: Set true when served over HTTPS, so the cookie is never sent in clear text.
    session_cookie_secure: bool = False
    #: Bearer token the ingest endpoints require. Empty turns ingest off.
    ingest_token: str = ""

    # --- JIRA -------------------------------------------------------------------
    # Read by scripts/sync_jira.py. Leave the base URL empty to use the local mock
    # (`--mock`) or file import. The token is never stored or returned.
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_api_version: str = "2"
    jira_jql: str = "issuetype in (Bug, Defect) AND created >= -90d ORDER BY created DESC"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def jira_live_enabled(self) -> bool:
        return bool(self.jira_base_url and self.jira_api_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
