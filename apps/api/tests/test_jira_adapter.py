"""JIRA field ids differ per instance, so the mapping is the thing under test."""

from __future__ import annotations

import pytest

from qa_dashboard.ingest.jira import FieldMapping, parse_issues

MAPPING = FieldMapping()


def rest_issue(**field_overrides: object) -> dict:
    fields = {
        "project": {"key": "QAD"},
        "summary": "Transfer confirmation page shows the wrong amount",
        "issuetype": {"name": "Bug"},
        "status": {"name": "Closed", "statusCategory": {"name": "Done"}},
        "priority": {"name": "High"},
        "components": [{"name": "Fund transfer"}],
        "customfield_10050": {"value": "Critical"},
        "customfield_10051": {"value": "production"},
        "customfield_10052": {"value": "Code defect"},
        "assignee": {"displayName": "Chen Wei"},
        "created": "2026-09-01T10:30:00.000+0800",
        "resolutiondate": "2026-09-03T16:00:00.000+0800",
    }
    fields.update(field_overrides)
    return {"key": "QAD-4101", "fields": fields}


def test_a_rest_search_response_is_parsed() -> None:
    defects = parse_issues({"issues": [rest_issue()]}, MAPPING)
    assert len(defects) == 1
    assert defects[0].key == "QAD-4101"
    assert defects[0].severity == "Critical"
    assert defects[0].component == "Fund transfer"
    assert defects[0].found_phase == "production"


def test_a_flat_issue_list_is_parsed() -> None:
    defects = parse_issues(
        [
            {
                "key": "QAD-1",
                "summary": "flat shape",
                "issue_type": "Bug",
                "severity": "Major",
                "component": "Login",
                "found_phase": "testing",
                "created_at": "2026-09-01T10:00:00",
            }
        ],
        MAPPING,
    )
    assert defects[0].severity == "Major"
    assert defects[0].component == "Login"


def test_the_jira_timezone_offset_is_understood() -> None:
    """JIRA writes +0800 without the colon that fromisoformat wants."""
    defect = parse_issues({"issues": [rest_issue()]}, MAPPING)[0]
    assert defect.created_at.day == 1
    assert defect.resolved_at is not None
    assert defect.resolved_at.day == 3


def test_severity_falls_back_to_priority_when_the_field_is_absent() -> None:
    issue = rest_issue()
    del issue["fields"]["customfield_10050"]
    assert parse_issues({"issues": [issue]}, MAPPING)[0].severity == "Critical"


def test_an_unmapped_priority_becomes_unknown_rather_than_guessing() -> None:
    issue = rest_issue(priority={"name": "Trivial-ish"})
    del issue["fields"]["customfield_10050"]
    assert parse_issues({"issues": [issue]}, MAPPING)[0].severity == "Unknown"


def test_non_bug_issue_types_are_dropped() -> None:
    assert parse_issues({"issues": [rest_issue(issuetype={"name": "Story"})]}, MAPPING) == []


def test_a_custom_bug_type_name_is_honoured() -> None:
    mapping = FieldMapping(bug_issue_types=["缺陷"])
    defects = parse_issues({"issues": [rest_issue(issuetype={"name": "缺陷"})]}, mapping)
    assert len(defects) == 1


def test_the_status_category_is_normalised() -> None:
    issue = rest_issue(status={"name": "In Progress", "statusCategory": {"name": "In Progress"}})
    assert parse_issues({"issues": [issue]}, MAPPING)[0].status_category == "in_progress"


def test_an_unresolved_issue_is_not_done() -> None:
    issue = rest_issue(
        status={"name": "Open", "statusCategory": {"name": "To Do"}}, resolutiondate=None
    )
    assert parse_issues({"issues": [issue]}, MAPPING)[0].status_category == "todo"


def test_an_unknown_found_phase_defaults_to_testing() -> None:
    issue = rest_issue(customfield_10051={"value": "somewhere-else"})
    assert parse_issues({"issues": [issue]}, MAPPING)[0].found_phase == "testing"


def test_a_custom_severity_field_id_is_read() -> None:
    mapping = FieldMapping(severity="customfield_10099")
    issue = rest_issue()
    issue["fields"]["customfield_10099"] = {"value": "Blocker"}
    assert parse_issues({"issues": [issue]}, mapping)[0].severity == "Blocker"


def test_a_browse_url_is_built_when_a_base_url_is_known() -> None:
    defects = parse_issues({"issues": [rest_issue()]}, MAPPING, base_url="https://jira.example/")
    assert defects[0].url == "https://jira.example/browse/QAD-4101"


def test_an_unusable_payload_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_issues({"not": "issues"}, MAPPING)
