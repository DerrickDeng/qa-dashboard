"""Adoption comes from the review verdict; accuracy comes from the Golden comparison."""

from __future__ import annotations

import pytest

from qa_dashboard.ingest.agent_logs import AgentLogFormatError, parse_logs


def log(**overrides: object) -> dict:
    payload: dict = {
        "run_id": "tc-001",
        "agent": "testcase-agent",
        "model": "claude-opus-5",
        "prompt_version": "v4",
        "started_at": "2026-09-11T02:14:00Z",
        "duration_ms": 18400,
        "input_ref": "LAB-101",
        "tokens": {"input": 7400, "output": 2100},
        "cost_usd": 0.042,
        "items": [
            {"item_id": "s1", "accepted": True, "edited": False, "edit_distance": 0},
            {"item_id": "s2", "accepted": True, "edited": True, "edit_distance": 34},
            {"item_id": "s3", "accepted": False, "edited": False, "edit_distance": 0},
        ],
        "comparison": {
            "golden_ref": "LAB-101",
            "golden_total": 9,
            "matched": 7,
            "missing": 2,
            "extra": 1,
            "hallucinated": 1,
        },
    }
    payload.update(overrides)
    return payload


def test_adoption_counts_only_accepted_items() -> None:
    run = parse_logs(log())[0]
    assert run.generated == 3
    assert run.accepted == 2
    assert run.rejected == 1


def test_unchanged_adoption_excludes_edited_items() -> None:
    run = parse_logs(log())[0]
    assert run.accepted_unchanged == 1
    assert run.edit_distance == 34


def test_the_golden_comparison_is_carried_through() -> None:
    run = parse_logs(log())[0]
    assert (run.golden_total, run.matched, run.missing, run.extra) == (9, 7, 2, 1)
    assert run.hallucinated == 1


def test_a_run_without_a_comparison_reports_no_accuracy_rather_than_zero() -> None:
    payload = log()
    del payload["comparison"]
    run = parse_logs(payload)[0]
    assert run.golden_total == 0
    assert run.matched == 0
    # Adoption still works; accuracy simply has no denominator for this run.
    assert run.accepted == 2


def test_a_run_without_items_still_records_the_comparison() -> None:
    payload = log()
    del payload["items"]
    run = parse_logs(payload)[0]
    assert run.generated == 0
    assert run.matched == 7


def test_an_array_of_logs_is_accepted() -> None:
    assert len(parse_logs([log(run_id="a"), log(run_id="b")])) == 2


def test_tokens_and_cost_are_read() -> None:
    run = parse_logs(log())[0]
    assert (run.input_tokens, run.output_tokens) == (7400, 2100)
    assert run.cost_usd == pytest.approx(0.042)


def test_a_log_without_a_run_id_is_refused() -> None:
    payload = log()
    del payload["run_id"]
    with pytest.raises(AgentLogFormatError):
        parse_logs(payload)


def test_a_log_without_an_agent_is_refused() -> None:
    payload = log()
    del payload["agent"]
    with pytest.raises(AgentLogFormatError):
        parse_logs(payload)
