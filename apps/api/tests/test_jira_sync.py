"""The sync path end to end: page through the mock JIRA, parse with the real mapping file."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from qa_dashboard.ingest.jira import FieldMapping, parse_issues
from qa_dashboard.ingest.jira_client import JiraConnection, JiraError, fetch_issues

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "mock-jira"))

import mock_jira  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
MAPPING = FieldMapping.load(REPO_ROOT / "samples" / "jira" / "field-mapping.json")


@pytest.fixture
def jira() -> TestClient:
    return TestClient(mock_jira.create_app(mock_jira.Store(today=date(2026, 9, 13), seed=11)))


def connection(**overrides: str) -> JiraConnection:
    values = {"base_url": "http://testserver", "token": mock_jira.TOKEN, **overrides}
    return JiraConnection(**values)


def test_fetch_follows_paging_to_the_end(jira: TestClient) -> None:
    total = jira.get(
        "/rest/api/2/search", headers=connection().headers(), params={"maxResults": 0}
    ).json()["total"]
    issues = fetch_issues(jira, connection(), "", page_size=9)
    assert len(issues) == total
    assert len({issue["key"] for issue in issues}) == total


def test_pages_are_reported_as_they_arrive(jira: TestClient) -> None:
    seen: list[tuple[int, int]] = []
    fetch_issues(
        jira, connection(), "project = SHOP", page_size=5, on_page=lambda a, b: seen.append((a, b))
    )
    assert seen
    assert seen[-1][0] == seen[-1][1]


def test_without_an_email_the_token_is_sent_as_bearer() -> None:
    assert connection().headers()["Authorization"].startswith("Bearer ")


def test_with_an_email_basic_auth_is_used(jira: TestClient) -> None:
    cloud = connection(email="me@example.test", api_version="3")
    assert cloud.headers()["Authorization"].startswith("Basic ")
    assert fetch_issues(jira, cloud, "project = QAD", page_size=50)


def test_a_bad_token_raises_with_jiras_reason(jira: TestClient) -> None:
    with pytest.raises(JiraError, match="401"):
        fetch_issues(jira, connection(token="wrong"), "")


def test_bad_jql_raises_with_jiras_message(jira: TestClient) -> None:
    with pytest.raises(JiraError, match="does not support this JQL"):
        fetch_issues(jira, connection(), "sprint in openSprints()")


def test_the_repository_mapping_file_matches_the_mock(jira: TestClient) -> None:
    """If this fails, samples/jira/field-mapping.json and the mock have drifted apart."""
    issues = fetch_issues(jira, connection(), "issuetype = Bug")
    defects = parse_issues({"issues": issues}, MAPPING)
    known = [item for item in defects if item.severity != "Unknown"]
    # A few bugs are filed without the custom fields; they fall back to priority.
    assert len(known) == len(defects)
    assert {item.found_phase for item in defects} >= {"testing", "production"}


def test_stories_and_tasks_are_not_counted_as_defects(jira: TestClient) -> None:
    issues = fetch_issues(jira, connection(), "")
    types = {issue["fields"]["issuetype"]["name"] for issue in issues}
    assert {"Story", "Task"} & types
    defects = parse_issues({"issues": issues}, MAPPING)
    assert {item.issue_type for item in defects} == {"Bug"}


def test_sparse_bugs_fall_back_to_priority_for_severity(jira: TestClient) -> None:
    issues = fetch_issues(jira, connection(), "issuetype = Bug")
    sparse = [issue for issue in issues if issue["fields"]["customfield_10050"] is None]
    assert sparse, "the mock should include bugs filed without custom fields"
    parsed = parse_issues({"issues": sparse}, MAPPING)
    assert all(item.severity != "Unknown" for item in parsed)
