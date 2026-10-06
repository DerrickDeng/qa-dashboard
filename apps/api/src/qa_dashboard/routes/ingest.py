"""Ingestion endpoints. CI pushes here; nothing polls outward."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import delete

from ..ingest import agent_logs, jira, playwright
from ..persistence.tables import AgentRun, Defect, TestResult, TestRun
from ..storage import BundleError, store_bundle
from .dependencies import DbSession, JiraMapping, require_ingest_token

# Only the bearer token opens these routes - never the session cookie.
# See dependencies.require_ingest_token for why.
router = APIRouter(
    prefix="/api/v1/ingest",
    tags=["ingest"],
    dependencies=[Depends(require_ingest_token)],
)


@router.post("/playwright", summary="Push a Playwright report from CI")
async def ingest_playwright(
    session: DbSession,
    report: Annotated[
        UploadFile, File(description="Playwright JSON report, or an HTML report index.html")
    ],
    bundle: Annotated[UploadFile | None, File(description="Zipped playwright-html folder")] = None,
    application_code: Annotated[str, Form()] = "",
    region: Annotated[str, Form()] = "",
    environment: Annotated[str, Form()] = "",
    product_type: Annotated[str, Form()] = "",
    job_name: Annotated[str, Form()] = "",
    build_number: Annotated[str, Form()] = "",
    branch: Annotated[str, Form()] = "",
    commit_sha: Annotated[str, Form()] = "",
    ci_url: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    raw = await report.read()
    payload = _decode_report(raw, report.filename or "")

    try:
        parsed = playwright.parse_report(payload)
    except playwright.ReportFormatError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    # Without CI there is no one to pass region and environment, so fall back to
    # the project name when it follows the region-environment convention.
    inferred = playwright.infer_region_environment(parsed)
    if inferred and not region.strip():
        region = inferred[0]
    if inferred and not environment.strip():
        environment = inferred[1]

    # Re-posting the same report replaces it rather than double-counting.
    session.execute(delete(TestResult).where(TestResult.run_id == parsed.run_id))
    session.execute(delete(TestRun).where(TestRun.id == parsed.run_id))

    stored_bundle = False
    if bundle is not None:
        try:
            store_bundle(parsed.run_id, await bundle.read())
            stored_bundle = True
        except BundleError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    session.add(
        TestRun(
            id=parsed.run_id,
            uploaded_at=datetime.now(UTC).replace(tzinfo=None),
            started_at=parsed.started_at,
            run_date=parsed.started_at.date(),
            duration_ms=parsed.duration_ms,
            application_code=application_code.strip().upper(),
            region=region.strip().lower(),
            environment=environment.strip().lower(),
            product_type=product_type.strip(),
            job_name=job_name or None,
            build_number=build_number or None,
            branch=branch or None,
            commit_sha=commit_sha or None,
            ci_url=ci_url or None,
            total=parsed.total,
            passed=parsed.count("passed"),
            failed=parsed.count("failed"),
            flaky=parsed.count("flaky"),
            skipped=parsed.count("skipped"),
            raw_report=json.dumps(payload, separators=(",", ":"), default=str),
            has_bundle=stored_bundle,
        )
    )

    for item in parsed.results:
        session.add(
            TestResult(
                run_id=parsed.run_id,
                run_date=parsed.started_at.date(),
                test_key=item.test_key[:600],
                file=item.file[:300],
                suite_path=item.suite_path[:400],
                title=item.title[:400],
                project_name=item.project_name[:120],
                feature=item.feature[:400],
                tags=item.tags[:500],
                status=item.status,
                duration_ms=item.duration_ms,
                retries=item.retries,
                error_message=item.error_message,
            )
        )

    return {
        "run_id": parsed.run_id,
        "total": parsed.total,
        "passed": parsed.count("passed"),
        "failed": parsed.count("failed"),
        "flaky": parsed.count("flaky"),
        "skipped": parsed.count("skipped"),
        "bundle_stored": stored_bundle,
        "region": region.strip().lower(),
        "environment": environment.strip().lower(),
    }


def _decode_report(raw: bytes, filename: str) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    if filename.endswith(".html") or text.lstrip()[:20].lower().startswith("<!doctype html"):
        try:
            return playwright.extract_report_json_from_html(text)
        except playwright.ReportFormatError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=422, detail=f"The report is not valid JSON: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="The report must be a JSON object.")
    return payload


@router.post("/jira", summary="Import JIRA issues from an export or a sync job")
async def ingest_jira(
    session: DbSession,
    mapping: JiraMapping,
    issues: Annotated[UploadFile, File(description="JIRA search response, or a flat issue list")],
    replace: Annotated[bool, Form()] = False,
    browse_base_url: Annotated[str, Form()] = "",
) -> dict[str, Any]:
    raw = await issues.read()
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        defects = jira.parse_issues(payload, mapping, base_url=browse_base_url)
    except (json.JSONDecodeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if replace:
        session.execute(delete(Defect))

    for item in defects:
        session.merge(
            Defect(
                key=item.key,
                project=item.project,
                summary=item.summary,
                issue_type=item.issue_type,
                status=item.status,
                status_category=item.status_category,
                severity=item.severity,
                priority=item.priority,
                component=item.component,
                found_phase=item.found_phase,
                root_cause=item.root_cause,
                assignee=item.assignee,
                reporter=item.reporter,
                created_at=item.created_at,
                resolved_at=item.resolved_at,
                url=item.url,
            )
        )

    return {"imported": len(defects)}


@router.post("/agent-runs", summary="Push agent run logs with their review outcome")
async def ingest_agent_runs(
    session: DbSession,
    logs: Annotated[UploadFile, File(description="One agent run log, or an array of them")],
) -> dict[str, Any]:
    raw = await logs.read()
    try:
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        runs = agent_logs.parse_logs(payload)
    except (json.JSONDecodeError, agent_logs.AgentLogFormatError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    for item in runs:
        session.merge(
            AgentRun(
                id=item.id,
                agent=item.agent,
                model=item.model,
                prompt_version=item.prompt_version,
                started_at=item.started_at,
                run_date=item.started_at.date(),
                duration_ms=item.duration_ms,
                input_ref=item.input_ref,
                generated=item.generated,
                accepted=item.accepted,
                accepted_unchanged=item.accepted_unchanged,
                rejected=item.rejected,
                edit_distance=item.edit_distance,
                golden_total=item.golden_total,
                matched=item.matched,
                missing=item.missing,
                extra=item.extra,
                hallucinated=item.hallucinated,
                input_tokens=item.input_tokens,
                output_tokens=item.output_tokens,
                cost_usd=item.cost_usd,
            )
        )

    return {"imported": len(runs)}
