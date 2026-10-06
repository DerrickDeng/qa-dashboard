"""The flaky score must separate "intermittent" from "just broken"."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from qa_dashboard.metrics.filters import Slice
from qa_dashboard.metrics.flaky import ranking
from qa_dashboard.persistence.db import configure_engine
from qa_dashboard.persistence.tables import TestResult, TestRun
from qa_dashboard.settings import Settings


@pytest.fixture
def session(tmp_path):  # type: ignore[no-untyped-def]
    engine = configure_engine(Settings(database_url=f"sqlite+pysqlite:///{tmp_path / 'flaky.db'}"))
    with Session(engine) as db:
        yield db


def add_history(db: Session, test_key: str, statuses: list[str]) -> None:
    """One run per status, oldest first, ending today."""
    for offset, status in enumerate(reversed(statuses)):
        run_date = date.today() - timedelta(days=offset)
        run_id = f"{test_key}-{offset}"
        db.add(
            TestRun(
                id=run_id,
                uploaded_at=datetime.now(),
                started_at=datetime.combine(run_date, datetime.min.time()),
                run_date=run_date,
                duration_ms=1000,
                total=1,
                passed=1 if status in ("passed", "flaky") else 0,
                failed=1 if status == "failed" else 0,
                flaky=1 if status == "flaky" else 0,
                skipped=0,
                raw_report="{}",
            )
        )
        db.add(
            TestResult(
                run_id=run_id,
                run_date=run_date,
                test_key=test_key,
                file="f.spec.js",
                title=test_key,
                project_name="hk-sit",
                feature="F",
                status=status,
                duration_ms=100,
                retries=1 if status == "flaky" else 0,
            )
        )
    db.commit()


WINDOW = Slice(days=30)


def test_an_always_failing_test_is_not_called_flaky(session: Session) -> None:
    add_history(session, "always-broken", ["failed"] * 8)
    assert ranking(session, WINDOW) == []


def test_an_always_passing_test_is_not_called_flaky(session: Session) -> None:
    add_history(session, "always-green", ["passed"] * 8)
    assert ranking(session, WINDOW) == []


def test_a_retry_rescued_test_is_flaky(session: Session) -> None:
    add_history(session, "retry-rescued", ["passed", "flaky", "passed", "flaky", "passed"])
    rows = ranking(session, WINDOW)
    assert [row["test_key"] for row in rows] == ["retry-rescued"]
    assert rows[0]["flaky_runs"] == 2


def test_a_flip_flopping_test_is_flaky(session: Session) -> None:
    add_history(session, "flip-flop", ["passed", "failed", "passed", "failed", "passed"])
    rows = ranking(session, WINDOW)
    assert rows[0]["flips"] == 4
    assert rows[0]["flaky_score"] > 0.5


def test_the_noisier_test_ranks_higher(session: Session) -> None:
    add_history(session, "very-noisy", ["passed", "failed", "passed", "failed", "flaky"])
    add_history(session, "slightly-noisy", ["passed", "passed", "passed", "passed", "flaky"])
    rows = ranking(session, WINDOW)
    assert [row["test_key"] for row in rows] == ["very-noisy", "slightly-noisy"]


def test_a_test_seen_too_few_times_is_held_back(session: Session) -> None:
    add_history(session, "barely-seen", ["passed", "failed"])
    assert ranking(session, WINDOW, min_runs=3) == []


def test_skipped_runs_do_not_create_false_flips(session: Session) -> None:
    add_history(session, "sometimes-skipped", ["passed", "skipped", "passed", "skipped", "passed"])
    assert ranking(session, WINDOW) == []


def test_recent_history_is_returned_oldest_first(session: Session) -> None:
    add_history(session, "history", ["passed", "failed", "passed", "failed", "passed"])
    assert ranking(session, WINDOW)[0]["recent"][-1] == "passed"
