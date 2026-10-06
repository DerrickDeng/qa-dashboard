"""Flaky-test ranking.

A test is unstable in two observable ways, and the ranking uses both:

1. **Retry flakiness** - Playwright itself marked the test `flaky`: it failed,
   was retried, and then passed inside the same run. This needs `retries > 0`
   configured, which the CI profile already does.
2. **Cross-run flip-flopping** - the test passes in one run and fails in the
   next without the test or the code changing. A test that is simply broken
   fails every time and is *not* flaky; it belongs in "top failures" instead.

The score is the share of runs where either signal fired:

    flaky_score = (flaky_runs + flips) / observed_runs

`flips` counts transitions between pass and fail across consecutive runs
ordered by start time, so a consistently red test scores 0 here and a test that
alternates scores close to 1. Tests seen fewer than `min_runs` times are held
back - two runs is not evidence of instability.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..persistence.tables import TestResult, TestRun
from .filters import Slice

PASS_LIKE = {"passed", "flaky"}


def ranking(
    session: Session,
    window: Slice,
    *,
    limit: int = 20,
    min_runs: int = 3,
) -> list[dict[str, Any]]:
    stmt = (
        select(
            TestResult.test_key,
            TestResult.title,
            TestResult.feature,
            TestResult.project_name,
            TestResult.file,
            TestResult.status,
            TestResult.retries,
            TestResult.error_message,
            TestRun.started_at,
        )
        .join(TestRun, TestRun.id == TestResult.run_id)
        .where(*window.run_conditions())
        .order_by(TestResult.test_key, TestRun.started_at)
    )

    grouped: dict[str, dict[str, Any]] = {}
    for (
        test_key,
        title,
        feature,
        project,
        file_name,
        status,
        retries,
        error,
        started_at,
    ) in session.execute(stmt):
        entry = grouped.setdefault(
            test_key,
            {
                "test_key": test_key,
                "title": title,
                "feature": feature,
                "project": project,
                "file": file_name,
                "history": [],
                "last_error": None,
                "total_retries": 0,
            },
        )
        entry["history"].append({"status": status, "started_at": started_at})
        entry["total_retries"] += int(retries or 0)
        if error:
            entry["last_error"] = error

    rows: list[dict[str, Any]] = []
    for entry in grouped.values():
        history = entry["history"]
        observed = len(history)
        if observed < min_runs:
            continue

        statuses = [item["status"] for item in history if item["status"] != "skipped"]
        if not statuses:
            continue

        flaky_runs = sum(1 for status in statuses if status == "flaky")
        failed_runs = sum(1 for status in statuses if status == "failed")
        flips = _count_flips(statuses)

        score = (flaky_runs + flips) / len(statuses)
        if score <= 0:
            continue

        rows.append(
            {
                "test_key": entry["test_key"],
                "title": entry["title"],
                "feature": entry["feature"],
                "project": entry["project"],
                "file": entry["file"],
                "runs": len(statuses),
                "flaky_runs": flaky_runs,
                "failed_runs": failed_runs,
                "flips": flips,
                "retries": entry["total_retries"],
                "flaky_score": round(score, 4),
                "last_error": entry["last_error"],
                "recent": [item["status"] for item in history[-12:]],
            }
        )

    rows.sort(key=lambda row: (row["flaky_score"], row["runs"]), reverse=True)
    return rows[:limit]


def _count_flips(statuses: list[str]) -> int:
    """Transitions between pass-like and fail across consecutive runs."""
    flips = 0
    for previous, current in zip(statuses, statuses[1:], strict=False):
        if (previous in PASS_LIKE) != (current in PASS_LIKE):
            flips += 1
    return flips


def daily_flaky_rate(session: Session, window: Slice) -> list[dict[str, Any]]:
    """Share of executed tests that Playwright marked flaky, per day."""
    stmt = (
        select(TestRun.run_date, TestRun.flaky, TestRun.total, TestRun.skipped)
        .where(*window.run_conditions())
        .order_by(TestRun.run_date)
    )

    by_day: dict[str, list[int]] = {}
    for run_date, flaky, total, skipped in session.execute(stmt):
        bucket = by_day.setdefault(run_date.isoformat(), [0, 0])
        bucket[0] += int(flaky)
        bucket[1] += int(total) - int(skipped)

    return [
        {
            "date": day,
            "flaky": flaky,
            "executed": executed,
            "flaky_rate": round(flaky / executed, 4) if executed else None,
        }
        for day, (flaky, executed) in sorted(by_day.items())
    ]
