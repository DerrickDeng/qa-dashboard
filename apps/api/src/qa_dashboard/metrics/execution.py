"""Test-execution metrics from the uploaded Playwright reports."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..persistence.tables import TestResult, TestRun
from .filters import Slice

#: Playwright's own outcome vocabulary. A flaky test passed, but only on a retry,
#: so it counts as a pass for the rate and is called out separately.
PASSING = ("passed", "flaky")


def _run_ids(session: Session, window: Slice) -> list[str]:
    stmt = select(TestRun.id).where(*window.run_conditions())
    return list(session.scalars(stmt))


def summary(session: Session, window: Slice) -> dict[str, Any]:
    """Headline counters for the most recent day that has data."""
    latest_day = session.scalar(select(func.max(TestRun.run_date)).where(*window.run_conditions()))
    if latest_day is None:
        return {
            "day": None,
            "runs": 0,
            "total": 0,
            "passed": 0,
            "failed": 0,
            "flaky": 0,
            "skipped": 0,
            "pass_rate": None,
            "previous_pass_rate": None,
        }

    today = _day_counters(session, window, latest_day)
    previous_day = session.scalar(
        select(func.max(TestRun.run_date)).where(
            *window.run_conditions(), TestRun.run_date < latest_day
        )
    )
    previous = _day_counters(session, window, previous_day) if previous_day else None

    return {
        "day": latest_day.isoformat(),
        **today,
        "previous_pass_rate": previous["pass_rate"] if previous else None,
    }


def _day_counters(session: Session, window: Slice, day: date) -> dict[str, Any]:
    row = session.execute(
        select(
            func.count(TestRun.id),
            func.coalesce(func.sum(TestRun.total), 0),
            func.coalesce(func.sum(TestRun.passed), 0),
            func.coalesce(func.sum(TestRun.failed), 0),
            func.coalesce(func.sum(TestRun.flaky), 0),
            func.coalesce(func.sum(TestRun.skipped), 0),
        ).where(*window.run_conditions(), TestRun.run_date == day)
    ).one()

    runs, total, passed, failed, flaky, skipped = (int(value) for value in row)
    executed = total - skipped
    return {
        "runs": runs,
        "total": total,
        "passed": passed,
        "failed": failed,
        "flaky": flaky,
        "skipped": skipped,
        "pass_rate": round((passed + flaky) / executed, 4) if executed else None,
    }


def daily_trend(session: Session, window: Slice) -> list[dict[str, Any]]:
    """One row per day: the counters plus the pass rate that day."""
    stmt = (
        select(
            TestRun.run_date,
            func.coalesce(func.sum(TestRun.total), 0),
            func.coalesce(func.sum(TestRun.passed), 0),
            func.coalesce(func.sum(TestRun.failed), 0),
            func.coalesce(func.sum(TestRun.flaky), 0),
            func.coalesce(func.sum(TestRun.skipped), 0),
        )
        .where(*window.run_conditions())
        .group_by(TestRun.run_date)
        .order_by(TestRun.run_date)
    )

    trend: list[dict[str, Any]] = []
    for run_date, total, passed, failed, flaky, skipped in session.execute(stmt):
        executed = int(total) - int(skipped)
        trend.append(
            {
                "date": run_date.isoformat(),
                "total": int(total),
                "passed": int(passed),
                "failed": int(failed),
                "flaky": int(flaky),
                "skipped": int(skipped),
                "pass_rate": round((int(passed) + int(flaky)) / executed, 4) if executed else None,
            }
        )
    return trend


def recent_runs(session: Session, window: Slice, limit: int = 25) -> list[dict[str, Any]]:
    """The run list behind "View report"."""
    stmt = (
        select(TestRun)
        .where(*window.run_conditions())
        .order_by(TestRun.started_at.desc())
        .limit(limit)
    )
    runs = []
    for run in session.scalars(stmt):
        executed = run.total - run.skipped
        runs.append(
            {
                "id": run.id,
                "started_at": run.started_at.isoformat(),
                "duration_ms": run.duration_ms,
                "application_code": run.application_code,
                "region": run.region,
                "environment": run.environment,
                "product_type": run.product_type,
                "job_name": run.job_name,
                "build_number": run.build_number,
                "branch": run.branch,
                "commit_sha": run.commit_sha,
                "ci_url": run.ci_url,
                "total": run.total,
                "passed": run.passed,
                "failed": run.failed,
                "flaky": run.flaky,
                "skipped": run.skipped,
                "pass_rate": round((run.passed + run.flaky) / executed, 4) if executed else None,
                "has_bundle": run.has_bundle,
            }
        )
    return runs


def by_project(session: Session, window: Slice) -> list[dict[str, Any]]:
    """Pass rate per Playwright project, which here is the region-environment pair."""
    run_ids = _run_ids(session, window)
    if not run_ids:
        return []

    stmt = (
        select(
            TestResult.project_name,
            func.count(TestResult.id),
            func.sum(case((TestResult.status.in_(PASSING), 1), else_=0)),
            func.sum(case((TestResult.status == "failed", 1), else_=0)),
            func.sum(case((TestResult.status == "flaky", 1), else_=0)),
            func.sum(case((TestResult.status == "skipped", 1), else_=0)),
        )
        .where(TestResult.run_id.in_(run_ids))
        .group_by(TestResult.project_name)
        .order_by(TestResult.project_name)
    )

    rows = []
    for project, total, passing, failed, flaky, skipped in session.execute(stmt):
        executed = int(total) - int(skipped)
        rows.append(
            {
                "project": project or "(none)",
                "total": int(total),
                "passed": int(passing) - int(flaky),
                "failed": int(failed),
                "flaky": int(flaky),
                "skipped": int(skipped),
                "pass_rate": round(int(passing) / executed, 4) if executed else None,
            }
        )
    return rows


def top_failures(session: Session, window: Slice, limit: int = 10) -> list[dict[str, Any]]:
    """Which tests fail most often in the window, with the latest error text."""
    run_ids = _run_ids(session, window)
    if not run_ids:
        return []

    stmt = (
        select(
            TestResult.test_key,
            func.max(TestResult.title),
            func.max(TestResult.feature),
            func.max(TestResult.project_name),
            func.count(TestResult.id),
            func.sum(case((TestResult.status == "failed", 1), else_=0)).label("failures"),
            func.max(TestResult.error_message),
        )
        .where(TestResult.run_id.in_(run_ids))
        .group_by(TestResult.test_key)
        .having(func.sum(case((TestResult.status == "failed", 1), else_=0)) > 0)
        .order_by(func.sum(case((TestResult.status == "failed", 1), else_=0)).desc())
        .limit(limit)
    )

    return [
        {
            "test_key": key,
            "title": title,
            "feature": feature,
            "project": project,
            "runs": int(runs),
            "failures": int(failures),
            "failure_rate": round(int(failures) / int(runs), 4) if runs else None,
            "error_message": error,
        }
        for key, title, feature, project, runs, failures, error in session.execute(stmt)
    ]
