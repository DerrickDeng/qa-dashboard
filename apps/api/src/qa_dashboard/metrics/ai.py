"""AI effectiveness: adoption and accuracy.

**Adoption** answers "did a human keep what the agent produced?" It is the
reviewer's verdict, so it only exists once a review has happened:

    adoption            = accepted / generated
    adoption_unchanged  = accepted_unchanged / generated     (kept with no edits)

The gap between the two is the real cost signal: a high adoption rate with a low
unchanged rate means people are keeping the output but rewriting it.

**Accuracy** answers "was it right?" and needs a reviewed Golden set to compare
against: feature files a person has already reviewed. Precision and
recall are reported separately, because one number hides the failure mode:

    precision = matched / (matched + extra)   -> of what it produced, how much was right
    recall    = matched / golden_total        -> of what it should have found, how much it found
    hallucination_rate = hallucinated / generated

A single "accuracy" figure is shown as F1, with both components always visible
beside it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..persistence.tables import AgentRun
from .filters import Slice


def _conditions(window: Slice) -> list[Any]:
    return [AgentRun.run_date >= window.start_date]


def _rate(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None or (precision + recall) == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 4)


def summary(session: Session, window: Slice) -> dict[str, Any]:
    row = session.execute(
        select(
            func.count(AgentRun.id),
            func.coalesce(func.sum(AgentRun.generated), 0),
            func.coalesce(func.sum(AgentRun.accepted), 0),
            func.coalesce(func.sum(AgentRun.accepted_unchanged), 0),
            func.coalesce(func.sum(AgentRun.edit_distance), 0),
            func.coalesce(func.sum(AgentRun.golden_total), 0),
            func.coalesce(func.sum(AgentRun.matched), 0),
            func.coalesce(func.sum(AgentRun.missing), 0),
            func.coalesce(func.sum(AgentRun.extra), 0),
            func.coalesce(func.sum(AgentRun.hallucinated), 0),
            func.coalesce(func.sum(AgentRun.cost_usd), 0.0),
            func.coalesce(func.sum(AgentRun.input_tokens + AgentRun.output_tokens), 0),
        ).where(*_conditions(window))
    ).one()

    (
        runs,
        generated,
        accepted,
        unchanged,
        edit_distance,
        golden_total,
        matched,
        missing,
        extra,
        hallucinated,
        cost,
        tokens,
    ) = row

    precision = _rate(matched, matched + extra)
    recall = _rate(matched, golden_total)

    return {
        "runs": int(runs),
        "generated": int(generated),
        "accepted": int(accepted),
        "accepted_unchanged": int(unchanged),
        "adoption": _rate(accepted, generated),
        "adoption_unchanged": _rate(unchanged, generated),
        "avg_edit_distance": _rate(edit_distance, accepted),
        "golden_total": int(golden_total),
        "matched": int(matched),
        "missing": int(missing),
        "extra": int(extra),
        "hallucinated": int(hallucinated),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "hallucination_rate": _rate(hallucinated, generated),
        "cost_usd": round(float(cost), 4),
        "tokens": int(tokens),
        "cost_per_accepted": _rate(float(cost), accepted),
    }


def daily_trend(session: Session, window: Slice) -> list[dict[str, Any]]:
    stmt = (
        select(
            AgentRun.run_date,
            func.coalesce(func.sum(AgentRun.generated), 0),
            func.coalesce(func.sum(AgentRun.accepted), 0),
            func.coalesce(func.sum(AgentRun.accepted_unchanged), 0),
            func.coalesce(func.sum(AgentRun.matched), 0),
            func.coalesce(func.sum(AgentRun.golden_total), 0),
            func.coalesce(func.sum(AgentRun.extra), 0),
        )
        .where(*_conditions(window))
        .group_by(AgentRun.run_date)
        .order_by(AgentRun.run_date)
    )

    trend = []
    for run_date, generated, accepted, unchanged, matched, golden, extra in session.execute(stmt):
        precision = _rate(int(matched), int(matched) + int(extra))
        recall = _rate(int(matched), int(golden))
        trend.append(
            {
                "date": run_date.isoformat(),
                "generated": int(generated),
                "accepted": int(accepted),
                "adoption": _rate(int(accepted), int(generated)),
                "adoption_unchanged": _rate(int(unchanged), int(generated)),
                "precision": precision,
                "recall": recall,
                "f1": _f1(precision, recall),
            }
        )
    return trend


def by_dimension(session: Session, window: Slice, column: Any) -> list[dict[str, Any]]:
    """Adoption and accuracy grouped by agent, model, or prompt version."""
    stmt = (
        select(
            column,
            func.count(AgentRun.id),
            func.coalesce(func.sum(AgentRun.generated), 0),
            func.coalesce(func.sum(AgentRun.accepted), 0),
            func.coalesce(func.sum(AgentRun.accepted_unchanged), 0),
            func.coalesce(func.sum(AgentRun.matched), 0),
            func.coalesce(func.sum(AgentRun.golden_total), 0),
            func.coalesce(func.sum(AgentRun.extra), 0),
            func.coalesce(func.sum(AgentRun.hallucinated), 0),
            func.coalesce(func.sum(AgentRun.cost_usd), 0.0),
        )
        .where(*_conditions(window))
        .group_by(column)
        .order_by(column)
    )

    rows = []
    for (
        name,
        runs,
        generated,
        accepted,
        unchanged,
        matched,
        golden,
        extra,
        hallucinated,
        cost,
    ) in session.execute(stmt):
        precision = _rate(int(matched), int(matched) + int(extra))
        recall = _rate(int(matched), int(golden))
        rows.append(
            {
                "name": str(name or "(none)"),
                "runs": int(runs),
                "generated": int(generated),
                "accepted": int(accepted),
                "adoption": _rate(int(accepted), int(generated)),
                "adoption_unchanged": _rate(int(unchanged), int(generated)),
                "precision": precision,
                "recall": recall,
                "f1": _f1(precision, recall),
                "hallucination_rate": _rate(int(hallucinated), int(generated)),
                "cost_usd": round(float(cost), 4),
            }
        )
    return rows


def recent(session: Session, window: Slice, limit: int = 25) -> list[dict[str, Any]]:
    stmt = (
        select(AgentRun)
        .where(*_conditions(window))
        .order_by(AgentRun.started_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": run.id,
            "agent": run.agent,
            "model": run.model,
            "prompt_version": run.prompt_version,
            "input_ref": run.input_ref,
            "started_at": run.started_at.isoformat(),
            "duration_ms": run.duration_ms,
            "generated": run.generated,
            "accepted": run.accepted,
            "accepted_unchanged": run.accepted_unchanged,
            "adoption": _rate(run.accepted, run.generated),
            "matched": run.matched,
            "missing": run.missing,
            "extra": run.extra,
            "hallucinated": run.hallucinated,
            "golden_total": run.golden_total,
            "precision": _rate(run.matched, run.matched + run.extra),
            "recall": _rate(run.matched, run.golden_total),
            "cost_usd": round(run.cost_usd, 4),
        }
        for run in session.scalars(stmt)
    ]
