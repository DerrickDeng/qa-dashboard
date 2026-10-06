"""The mock JIRA must behave like JIRA where the sync job depends on it.

It lives in apps/mock-jira and shares this Python environment, so its tests run
here rather than in a project of their own.
"""

from __future__ import annotations

import base64
import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mock-jira"))

import mock_jira  # noqa: E402

BEARER = {"Authorization": f"Bearer {mock_jira.TOKEN}"}


@pytest.fixture
def jira() -> TestClient:
    store = mock_jira.Store(today=date(2026, 9, 13), seed=7)
    return TestClient(mock_jira.create_app(store))


def search(client: TestClient, jql: str = "", **params: object):  # type: ignore[no-untyped-def]
    return client.get("/rest/api/2/search", params={"jql": jql, **params}, headers=BEARER)


def test_search_requires_credentials(jira: TestClient) -> None:
    assert jira.get("/rest/api/2/search").status_code == 401


def test_a_wrong_token_is_refused(jira: TestClient) -> None:
    response = jira.get("/rest/api/2/search", headers={"Authorization": "Bearer nope"})
    assert response.status_code == 401


def test_basic_auth_with_the_token_as_password_is_accepted(jira: TestClient) -> None:
    pair = base64.b64encode(f"me@example.test:{mock_jira.TOKEN}".encode()).decode()
    response = jira.get("/rest/api/3/search", headers={"Authorization": f"Basic {pair}"})
    assert response.status_code == 200


def test_paging_returns_every_issue_exactly_once(jira: TestClient) -> None:
    total = search(jira).json()["total"]
    keys: list[str] = []
    start = 0
    while start < total:
        page = search(jira, startAt=start, maxResults=17).json()
        keys += [issue["key"] for issue in page["issues"]]
        start += len(page["issues"])
    assert len(keys) == total
    assert len(set(keys)) == total


def test_max_results_is_capped_like_jira(jira: TestClient) -> None:
    assert search(jira, maxResults=5000).json()["maxResults"] == mock_jira.MAX_RESULTS_CAP


def test_the_response_uses_jira_shapes_and_opaque_field_ids(jira: TestClient) -> None:
    issue = search(jira, "issuetype = Bug").json()["issues"][0]
    fields = issue["fields"]
    assert set(fields["status"]) == {"name", "statusCategory"}
    assert "customfield_10050" in fields
    # JIRA writes +0800 without a colon.
    assert fields["created"].endswith("+0800")


def test_project_and_issuetype_filters(jira: TestClient) -> None:
    issues = search(jira, "project = SHOP AND issuetype in (Story, Task)").json()["issues"]
    assert issues
    assert {issue["fields"]["project"]["key"] for issue in issues} == {"SHOP"}
    assert {issue["fields"]["issuetype"]["name"] for issue in issues} <= {"Story", "Task"}


def test_a_relative_created_filter(jira: TestClient) -> None:
    recent = search(jira, "created >= -7d").json()["total"]
    everything = search(jira).json()["total"]
    assert 0 < recent < everything


def test_status_category_filter(jira: TestClient) -> None:
    issues = search(jira, "statusCategory = Done").json()["issues"]
    assert issues
    assert all(issue["fields"]["resolutiondate"] for issue in issues)


def test_order_by_created_ascending(jira: TestClient) -> None:
    created = [
        issue["fields"]["created"]
        for issue in search(jira, "ORDER BY created ASC", maxResults=50).json()["issues"]
    ]
    assert created == sorted(created)


def test_unsupported_jql_is_refused_like_jira(jira: TestClient) -> None:
    response = search(jira, "sprint in openSprints()")
    assert response.status_code == 400
    assert "errorMessages" in response.json()["detail"]


def test_the_field_list_names_the_custom_fields(jira: TestClient) -> None:
    fields = jira.get("/rest/api/2/field", headers=BEARER).json()
    by_name = {item["name"]: item["id"] for item in fields}
    assert by_name["Severity"] == "customfield_10050"
    assert by_name["Found In Phase"] == "customfield_10051"


def test_a_created_bug_is_searchable_and_can_be_closed(jira: TestClient) -> None:
    created = jira.post(
        "/rest/api/2/issue",
        headers=BEARER,
        json={
            "fields": {
                "project": {"key": "QAD"},
                "issuetype": {"name": "Bug"},
                "summary": "A newly reported defect",
                "components": [{"name": "Login"}],
                "customfield_10050": {"value": "Critical"},
                "customfield_10051": {"value": "production"},
            }
        },
    )
    assert created.status_code == 201
    key = created.json()["key"]

    found = search(jira, "project = QAD ORDER BY created DESC").json()["issues"]
    assert any(issue["key"] == key for issue in found)

    closed = jira.post(
        f"/rest/api/2/issue/{key}/transitions",
        headers=BEARER,
        json={"transition": {"id": mock_jira.DONE_TRANSITION_ID}},
    )
    assert closed.status_code == 204
    done = search(jira, "statusCategory = Done").json()["issues"]
    assert any(issue["key"] == key for issue in done)


def test_the_browse_page_resolves(jira: TestClient) -> None:
    key = search(jira).json()["issues"][0]["key"]
    assert jira.get(f"/browse/{key}").status_code == 200


def test_the_data_is_repeatable_for_the_same_seed_and_day() -> None:
    first = mock_jira.Store(today=date(2026, 9, 13), seed=3)
    second = mock_jira.Store(today=date(2026, 9, 13), seed=3)
    assert list(first.issues) == list(second.issues)
