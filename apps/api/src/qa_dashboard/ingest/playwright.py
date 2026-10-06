"""Parse a Playwright report into a run plus flattened per-test rows.

Two report shapes are accepted, because a Jenkins job may have either at hand:

**A. The `json` reporter** (`--reporter=json`, or a `['json', {outputFile}]` entry
in `playwright.config.ts`). Nested `suites` -> `specs` -> `tests` -> `results`.
This is the documented, stable contract and the recommended one.

**B. The HTML reporter's internal `report.json`.** Flat `files[] -> tests[]`,
found inside the base64 zip at the end of `playwright-html/index.html`. Accepted
so an existing pipeline can push without changing its Playwright config.

In a playwright-bdd project one "test" is one Scenario: the describe path holds
the Feature name and `tags` holds the BDD tags, so both are kept for grouping.
Playwright's outcome vocabulary maps straight through:
`expected -> passed`, `unexpected -> failed`, `flaky`, `skipped`.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

#: A project named region-environment, such as `hk-sit` or `sg-uat`.
PROJECT_PATTERN = re.compile(r"^([a-z]{2,})-([a-z]{2,})$", re.IGNORECASE)

#: Terminal colour codes Playwright embeds in assertion messages.
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

STATUS_MAP = {
    "expected": "passed",
    "unexpected": "failed",
    "flaky": "flaky",
    "skipped": "skipped",
}


class ReportFormatError(ValueError):
    """The uploaded file is not a Playwright report this parser understands."""


@dataclass
class ParsedResult:
    test_key: str
    file: str
    suite_path: str
    title: str
    project_name: str
    feature: str
    tags: str
    status: str
    duration_ms: int
    retries: int
    error_message: str | None


@dataclass
class ParsedRun:
    run_id: str
    started_at: datetime
    duration_ms: int
    results: list[ParsedResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    def count(self, status: str) -> int:
        return sum(1 for item in self.results if item.status == status)


def parse_report(payload: dict[str, Any], *, run_id: str | None = None) -> ParsedRun:
    """Detect the shape and parse it."""
    if not isinstance(payload, dict):
        raise ReportFormatError("The report must be a JSON object.")

    if isinstance(payload.get("suites"), list):
        run = _parse_json_reporter(payload)
    elif isinstance(payload.get("files"), list):
        run = _parse_html_report_json(payload)
    else:
        raise ReportFormatError(
            "Unrecognised Playwright report. Expected either the json reporter "
            "output (top-level 'suites') or the HTML report's report.json "
            "(top-level 'files'). Generate the first with: "
            "npx playwright test --reporter=json"
        )

    run.run_id = run_id or _derive_run_id(payload, run.started_at)
    return run


def extract_report_json_from_html(html: str) -> dict[str, Any]:
    """Pull the report out of a Playwright HTML report's index.html.

    The HTML reporter appends a base64 `data:application/zip` payload holding
    `report.json` plus one `<fileId>.json` per spec file. `report.json` alone is
    only a summary: its per-test `results` carry attachments, but no status and
    no errors. The per-file JSON has the full results, so they are merged back in
    by `testId` - otherwise a failure would arrive with no error message.
    """
    match = re.search(r"data:application/zip;base64,([A-Za-z0-9+/=\s]+)", html)
    if not match:
        raise ReportFormatError("No embedded report data found in this index.html.")

    blob = base64.b64decode(re.sub(r"\s+", "", match.group(1)))
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = set(archive.namelist())
        if "report.json" not in names:
            raise ReportFormatError("The embedded report has no report.json.")
        with archive.open("report.json") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ReportFormatError("The embedded report.json is not an object.")

        for entry in data.get("files") or []:
            detail_name = f"{entry.get('fileId')}.json"
            if detail_name not in names:
                continue
            with archive.open(detail_name) as handle:
                detail = json.load(handle)
            full_by_id = {test.get("testId"): test for test in detail.get("tests") or []}
            for test in entry.get("tests") or []:
                full = full_by_id.get(test.get("testId"))
                if full and isinstance(full.get("results"), list):
                    test["results"] = full["results"]
    return data


def infer_region_environment(run: ParsedRun) -> tuple[str, str] | None:
    """Read region and environment off a project named like `hk-sit`.

    Only when every test in the run belongs to one such project; a run spanning
    several projects has no single answer, so nothing is guessed.
    """
    projects = {item.project_name for item in run.results if item.project_name}
    if len(projects) != 1:
        return None
    match = PROJECT_PATTERN.match(projects.pop())
    return (match.group(1), match.group(2)) if match else None


# --- Shape A: the json reporter -------------------------------------------------


def _parse_json_reporter(payload: dict[str, Any]) -> ParsedRun:
    stats = payload.get("stats") or {}
    run = ParsedRun(
        run_id="",
        started_at=_parse_time(stats.get("startTime")),
        duration_ms=int(stats.get("duration") or 0),
    )
    for suite in payload.get("suites") or []:
        _walk_suite(suite, [], run)
    return run


def _walk_suite(suite: dict[str, Any], ancestors: list[str], run: ParsedRun) -> None:
    title = str(suite.get("title") or "")
    file_name = str(suite.get("file") or "")
    # Every suite carries `file`; the file-level suite is the one whose title IS
    # the file. Describe blocks below it share the file but have their own title,
    # and those titles are the describe path (the Feature name, under playwright-bdd).
    is_file_suite = bool(file_name) and title == file_name
    path = ancestors if (is_file_suite or not title) else [*ancestors, title]

    for spec in suite.get("specs") or []:
        _collect_spec(spec, suite, path, run)
    for child in suite.get("suites") or []:
        _walk_suite(child, path, run)


def _collect_spec(
    spec: dict[str, Any],
    suite: dict[str, Any],
    suite_path: list[str],
    run: ParsedRun,
) -> None:
    file_name = str(spec.get("file") or suite.get("file") or "")
    title = str(spec.get("title") or "")
    spec_tags = _tags(spec.get("tags"))

    for test in spec.get("tests") or []:
        results = test.get("results") or []
        run.results.append(
            ParsedResult(
                test_key=_test_key(
                    file_name, suite_path, title, str(test.get("projectName") or "")
                ),
                file=file_name,
                suite_path=" › ".join(suite_path),
                title=title,
                project_name=str(test.get("projectName") or ""),
                feature=suite_path[0] if suite_path else "",
                tags=spec_tags or _tags(test.get("tags")),
                status=STATUS_MAP.get(str(test.get("status") or ""), "failed"),
                duration_ms=sum(int(item.get("duration") or 0) for item in results),
                retries=max(0, len(results) - 1),
                error_message=_first_error(results),
            )
        )


# --- Shape B: the HTML reporter's report.json -----------------------------------


def _parse_html_report_json(payload: dict[str, Any]) -> ParsedRun:
    run = ParsedRun(
        run_id="",
        started_at=_parse_time(payload.get("startTime")),
        duration_ms=int(float(payload.get("duration") or 0)),
    )

    for entry in payload.get("files") or []:
        file_name = str(entry.get("fileName") or "")
        for test in entry.get("tests") or []:
            path = [str(item) for item in (test.get("path") or [])]
            results = test.get("results") or []
            project_name = str(test.get("projectName") or "")
            run.results.append(
                ParsedResult(
                    test_key=_test_key(file_name, path, str(test.get("title") or ""), project_name),
                    file=file_name,
                    suite_path=" › ".join(path),
                    title=str(test.get("title") or ""),
                    project_name=project_name,
                    feature=path[0] if path else "",
                    tags=_tags(test.get("tags")),
                    status=STATUS_MAP.get(str(test.get("outcome") or ""), "failed"),
                    duration_ms=int(test.get("duration") or 0),
                    retries=max(0, len(results) - 1),
                    error_message=_first_error(results),
                )
            )
    return run


# --- Shared helpers -------------------------------------------------------------


def _tags(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value if str(item).strip())
    return ""


def _first_error(results: list[dict[str, Any]]) -> str | None:
    for result in results:
        for error in result.get("errors") or []:
            message = _clean(error.get("message"))
            if message:
                return message
        error_obj = result.get("error")
        if isinstance(error_obj, dict):
            message = _clean(error_obj.get("message"))
            if message:
                return message
    return None


def _clean(message: object) -> str:
    return ANSI_ESCAPE.sub("", str(message or "")).strip()[:4000]


def _test_key(file_name: str, suite_path: list[str], title: str, project: str) -> str:
    """Identity of a test across runs. Project is included: hk-sit and sg-uat are
    different tests for flaky purposes, even with the same scenario title."""
    return " › ".join([part for part in [file_name, *suite_path, title, project] if part])


def _parse_time(value: object) -> datetime:
    if isinstance(value, int | float) and value > 0:
        # The HTML report writes startTime as epoch milliseconds.
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC).replace(tzinfo=None)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.now(UTC).replace(tzinfo=None)


def _derive_run_id(payload: dict[str, Any], started_at: datetime) -> str:
    """Content-derived id, so re-posting the same report is idempotent."""
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    return f"{started_at:%Y%m%dT%H%M%S}-{digest[:12]}"
