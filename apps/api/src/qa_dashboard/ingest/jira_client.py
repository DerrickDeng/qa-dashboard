"""Page through a JIRA search, for the sync job.

Kept separate from the parser so the parsing stays pure and this part can be
pointed at the local mock JIRA, a real instance, or a test client alike.

Auth follows the two JIRA flavours: with an email it is Basic (email + API token,
as Jira Cloud expects); without one it is Bearer (a personal access token, as
Jira Data Center expects).

Note for Jira Cloud: newer Cloud sites moved search to `/rest/api/3/search/jql`,
which pages with `nextPageToken` instead of `startAt`. Data Center keeps
`/rest/api/2/search`. Confirm which one your instance serves before switching
from the mock.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


class JiraError(RuntimeError):
    """JIRA refused the request. The message carries JIRA's own explanation."""


@dataclass(frozen=True)
class JiraConnection:
    base_url: str
    token: str
    email: str = ""
    api_version: str = "2"

    def headers(self) -> dict[str, str]:
        if self.email:
            pair = base64.b64encode(f"{self.email}:{self.token}".encode()).decode()
            authorization = f"Basic {pair}"
        else:
            authorization = f"Bearer {self.token}"
        return {"Authorization": authorization, "Accept": "application/json"}

    @property
    def search_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/rest/api/{self.api_version}/search"


def fetch_issues(
    client: httpx.Client,
    connection: JiraConnection,
    jql: str,
    *,
    page_size: int = 100,
    max_pages: int = 200,
    on_page: Callable[[int, int], None] | None = None,
) -> list[dict[str, Any]]:
    """Every issue matching `jql`, following startAt paging to the end."""
    issues: list[dict[str, Any]] = []
    start_at = 0

    for _ in range(max_pages):
        response = client.get(
            connection.search_url,
            params={"jql": jql, "startAt": start_at, "maxResults": page_size},
            headers=connection.headers(),
        )
        if response.status_code >= 400:
            raise JiraError(_explain(response))

        body = response.json()
        batch = [item for item in body.get("issues") or [] if isinstance(item, dict)]
        issues.extend(batch)
        total = int(body.get("total") or 0)
        if on_page:
            on_page(len(issues), total)

        start_at += len(batch)
        if not batch or start_at >= total:
            return issues

    raise JiraError(f"Stopped after {max_pages} pages; narrow the JQL.")


def _explain(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"JIRA answered {response.status_code}."
    detail = body.get("detail", body) if isinstance(body, dict) else body
    if isinstance(detail, dict):
        messages = detail.get("errorMessages") or list((detail.get("errors") or {}).values())
        if messages:
            return f"JIRA answered {response.status_code}: {'; '.join(map(str, messages))}"
    return f"JIRA answered {response.status_code}: {detail}"
