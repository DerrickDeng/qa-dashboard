"""Read endpoints. One per dashboard section, plus the filter options and run detail."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import distinct, select

from ..metrics import ai, defects, execution, flaky
from ..persistence.tables import AgentRun, TestRun
from ..storage import bundle_entry_point
from .dependencies import CurrentSlice, DbSession, current_user

# Everything here is for people, so everything needs a signed-in session.
router = APIRouter(prefix="/api/v1", tags=["dashboard"], dependencies=[Depends(current_user)])


@router.get("/filters", summary="Values available in the filter row")
def filters(session: DbSession) -> dict[str, Any]:
    def values(column: Any) -> list[str]:
        return sorted(
            {str(value) for (value,) in session.execute(select(distinct(column))) if value}
        )

    return {
        "application_codes": values(TestRun.application_code),
        "regions": values(TestRun.region),
        "environments": values(TestRun.environment),
        "agents": values(AgentRun.agent),
        "models": values(AgentRun.model),
        "prompt_versions": values(AgentRun.prompt_version),
    }


@router.get("/execution", summary="Test-execution section")
def execution_section(session: DbSession, window: CurrentSlice) -> dict[str, Any]:
    return {
        "summary": execution.summary(session, window),
        "trend": execution.daily_trend(session, window),
        "by_project": execution.by_project(session, window),
        "runs": execution.recent_runs(session, window),
        "top_failures": execution.top_failures(session, window),
        "flaky_ranking": flaky.ranking(session, window),
        "flaky_trend": flaky.daily_flaky_rate(session, window),
    }


@router.get("/defects", summary="Defect section")
def defects_section(session: DbSession, window: CurrentSlice) -> dict[str, Any]:
    return {
        "summary": defects.summary(session, window),
        "trend": defects.daily_trend(session, window),
        "by_severity": defects.by_severity(session, window),
        "by_component": defects.by_component(session, window),
        "by_found_phase": defects.by_found_phase(session, window),
        "by_status": defects.by_status(session, window),
        "by_root_cause": defects.by_root_cause(session, window),
        "ageing": defects.ageing(session),
        "recent": defects.recent(session, window),
    }


@router.get("/ai", summary="AI effectiveness section")
def ai_section(session: DbSession, window: CurrentSlice) -> dict[str, Any]:
    return {
        "summary": ai.summary(session, window),
        "trend": ai.daily_trend(session, window),
        "by_agent": ai.by_dimension(session, window, AgentRun.agent),
        "by_model": ai.by_dimension(session, window, AgentRun.model),
        "by_prompt_version": ai.by_dimension(session, window, AgentRun.prompt_version),
        "recent": ai.recent(session, window),
    }


@router.get("/runs/{run_id}", summary="One run, with its full report payload")
def run_detail(session: DbSession, run_id: str) -> dict[str, Any]:
    run = session.get(TestRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} was not found.")

    return {
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
        "has_bundle": run.has_bundle,
        "bundle_url": bundle_entry_point(run.id) if run.has_bundle else None,
        "report": json.loads(run.raw_report),
    }
