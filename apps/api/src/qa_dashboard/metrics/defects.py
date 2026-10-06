"""Defect metrics from the ingested JIRA issues.

The dashboard question is "what kind of defects do we have, and are we keeping
up?" - so the numbers are classification breakdowns plus an open/closed trend.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ingest.jira import PHASE_ORDER, SEVERITY_ORDER
from ..persistence.tables import Defect
from .filters import Slice

#: Open defects older than this are called out as ageing.
AGE_BUCKETS = [
    (0, 7, "0-7 days"),
    (7, 14, "7-14 days"),
    (14, 30, "14-30 days"),
    (30, 9999, "30+ days"),
]


def _window_conditions(window: Slice) -> list[Any]:
    start = datetime.combine(window.start_date, time.min)
    conditions: list[Any] = [Defect.created_at >= start]
    if window.application_code:
        conditions.append(Defect.project == window.application_code)
    return conditions


def summary(session: Session, window: Slice) -> dict[str, Any]:
    start = datetime.combine(window.start_date, time.min)

    created = session.scalar(select(func.count(Defect.key)).where(*_window_conditions(window))) or 0
    resolved = (
        session.scalar(
            select(func.count(Defect.key)).where(
                Defect.resolved_at.is_not(None), Defect.resolved_at >= start
            )
        )
        or 0
    )
    open_now = (
        session.scalar(select(func.count(Defect.key)).where(Defect.status_category != "done")) or 0
    )
    open_critical = (
        session.scalar(
            select(func.count(Defect.key)).where(
                Defect.status_category != "done",
                Defect.severity.in_(["Blocker", "Critical"]),
            )
        )
        or 0
    )

    total_all = session.scalar(select(func.count(Defect.key))) or 0
    escaped = (
        session.scalar(select(func.count(Defect.key)).where(Defect.found_phase == "production"))
        or 0
    )

    return {
        "created": int(created),
        "resolved": int(resolved),
        "open": int(open_now),
        "open_critical": int(open_critical),
        "escape_rate": round(int(escaped) / int(total_all), 4) if total_all else None,
        "escaped": int(escaped),
        "total": int(total_all),
        "mttr_days": _mttr_days(session, window),
    }


def _mttr_days(session: Session, window: Slice) -> float | None:
    start = datetime.combine(window.start_date, time.min)
    rows = session.execute(
        select(Defect.created_at, Defect.resolved_at).where(
            Defect.resolved_at.is_not(None), Defect.resolved_at >= start
        )
    ).all()
    if not rows:
        return None
    total = sum(float((resolved - created).total_seconds()) for created, resolved in rows)
    return round(total / len(rows) / 86400, 2)


def _breakdown(
    session: Session, column: Any, window: Slice, order: list[str] | None = None
) -> list[dict[str, Any]]:
    stmt = (
        select(column, func.count(Defect.key)).where(*_window_conditions(window)).group_by(column)
    )
    counts = {str(name or "Unclassified"): int(value) for name, value in session.execute(stmt)}

    if order:
        names = [name for name in order if name in counts]
        names += sorted(name for name in counts if name not in order)
    else:
        names = sorted(counts, key=lambda name: counts[name], reverse=True)

    return [{"name": name, "count": counts[name]} for name in names]


def by_severity(session: Session, window: Slice) -> list[dict[str, Any]]:
    return _breakdown(session, Defect.severity, window, SEVERITY_ORDER)


def by_component(session: Session, window: Slice, limit: int = 10) -> list[dict[str, Any]]:
    return _breakdown(session, Defect.component, window)[:limit]


def by_found_phase(session: Session, window: Slice) -> list[dict[str, Any]]:
    return _breakdown(session, Defect.found_phase, window, PHASE_ORDER)


def by_status(session: Session, window: Slice) -> list[dict[str, Any]]:
    return _breakdown(session, Defect.status_category, window, ["todo", "in_progress", "done"])


def by_root_cause(session: Session, window: Slice, limit: int = 8) -> list[dict[str, Any]]:
    return _breakdown(session, Defect.root_cause, window)[:limit]


def daily_trend(session: Session, window: Slice) -> list[dict[str, Any]]:
    """New, resolved, and still-open counts per day."""
    days = [window.start_date + timedelta(days=offset) for offset in range(window.days)]
    days = [day for day in days if day <= date.today()]

    created_by_day: dict[date, int] = {}
    for (created_at,) in session.execute(
        select(Defect.created_at).where(*_window_conditions(window))
    ):
        created_by_day[created_at.date()] = created_by_day.get(created_at.date(), 0) + 1

    resolved_by_day: dict[date, int] = {}
    for (resolved_at,) in session.execute(
        select(Defect.resolved_at).where(Defect.resolved_at.is_not(None))
    ):
        resolved_by_day[resolved_at.date()] = resolved_by_day.get(resolved_at.date(), 0) + 1

    all_defects = session.execute(select(Defect.created_at, Defect.resolved_at)).all()

    trend = []
    for day in days:
        end = datetime.combine(day, time.max)
        still_open = sum(
            1
            for created, resolved in all_defects
            if created <= end and (resolved is None or resolved > end)
        )
        trend.append(
            {
                "date": day.isoformat(),
                "created": created_by_day.get(day, 0),
                "resolved": resolved_by_day.get(day, 0),
                "open": still_open,
            }
        )
    return trend


def ageing(session: Session) -> list[dict[str, Any]]:
    """Open defects bucketed by how long they have been open."""
    now = datetime.now()
    rows = session.execute(select(Defect.created_at).where(Defect.status_category != "done")).all()

    buckets = {label: 0 for _, _, label in AGE_BUCKETS}
    for (created_at,) in rows:
        age_days = (now - created_at).days
        for low, high, label in AGE_BUCKETS:
            if low <= age_days < high:
                buckets[label] += 1
                break

    return [{"name": label, "count": buckets[label]} for _, _, label in AGE_BUCKETS]


def recent(session: Session, window: Slice, limit: int = 25) -> list[dict[str, Any]]:
    stmt = (
        select(Defect)
        .where(*_window_conditions(window))
        .order_by(Defect.created_at.desc())
        .limit(limit)
    )
    return [
        {
            "key": item.key,
            "summary": item.summary,
            "severity": item.severity,
            "component": item.component,
            "found_phase": item.found_phase,
            "status": item.status,
            "status_category": item.status_category,
            "assignee": item.assignee,
            "created_at": item.created_at.isoformat(),
            "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
            "url": item.url,
        }
        for item in session.scalars(stmt)
    ]
