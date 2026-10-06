"""Turn JIRA issues into defect rows.

Two shapes are accepted, because JIRA instances differ:

1. **Raw JIRA REST** - `{"issues": [{"key": ..., "fields": {...}}]}`, exactly what
   `/rest/api/3/search` returns and what "Export -> JSON" produces.
2. **Flat** - a list of plain objects whose keys already match the defect fields.

Which JIRA field carries severity, component, or the phase a defect was found in
differs per instance, so the mapping lives in `FieldMapping` and is loaded from
`samples/jira/field-mapping.json` (or whatever path the caller passes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DONE_CATEGORIES = {"done", "complete", "completed", "resolved", "closed"}
IN_PROGRESS_CATEGORIES = {"in progress", "indeterminate", "in-progress"}

#: Severity order, worst first. Anything unrecognised lands in "Unknown".
SEVERITY_ORDER = ["Blocker", "Critical", "Major", "Minor", "Trivial", "Unknown"]

#: Where the defect was found. "production" is what the escape rate counts.
PHASE_ORDER = ["requirement", "development", "testing", "staging", "production"]


@dataclass
class FieldMapping:
    """Which JIRA field id holds each dashboard concept."""

    # Defaults match the local mock JIRA and samples/jira/field-mapping.json.
    # A real instance will use different ids; set them in the mapping file.
    severity: str = "customfield_10050"
    found_phase: str = "customfield_10051"
    root_cause: str = "customfield_10052"
    component: str = "components"
    bug_issue_types: list[str] = field(default_factory=lambda: ["Bug", "Defect", "缺陷", "故障"])
    #: Fallback: derive severity from priority when no severity field exists.
    severity_from_priority: dict[str, str] = field(
        default_factory=lambda: {
            "Highest": "Blocker",
            "High": "Critical",
            "Medium": "Major",
            "Low": "Minor",
            "Lowest": "Trivial",
        }
    )

    @classmethod
    def load(cls, path: Path | None) -> FieldMapping:
        if path is None or not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = {key: raw[key] for key in raw if key in cls.__dataclass_fields__}
        return cls(**known)


@dataclass
class ParsedDefect:
    key: str
    project: str | None
    summary: str
    issue_type: str
    status: str
    status_category: str
    severity: str
    priority: str | None
    component: str
    found_phase: str
    root_cause: str | None
    assignee: str | None
    reporter: str | None
    created_at: datetime
    resolved_at: datetime | None
    url: str | None


def parse_issues(
    payload: Any,
    mapping: FieldMapping,
    *,
    base_url: str = "",
) -> list[ParsedDefect]:
    issues = _as_issue_list(payload)
    defects: list[ParsedDefect] = []

    for issue in issues:
        raw_fields = issue.get("fields")
        fields: dict[str, Any] = raw_fields if isinstance(raw_fields, dict) else issue
        issue_type = _name_of(fields.get("issuetype")) or str(fields.get("issue_type") or "Bug")
        if mapping.bug_issue_types and issue_type not in mapping.bug_issue_types:
            continue

        key = str(issue.get("key") or fields.get("key") or "")
        if not key:
            continue

        defects.append(
            ParsedDefect(
                key=key,
                project=_project_of(issue, fields, key),
                summary=str(fields.get("summary") or "")[:600],
                issue_type=issue_type,
                status=_name_of(fields.get("status")) or str(fields.get("status") or ""),
                status_category=_status_category(fields),
                severity=_severity(fields, mapping),
                priority=_name_of(fields.get("priority")) or _opt_str(fields.get("priority")),
                component=_component(fields, mapping),
                found_phase=_found_phase(fields, mapping),
                root_cause=_field_value(fields, mapping.root_cause)
                or _opt_str(fields.get("root_cause")),
                assignee=_display_name(fields.get("assignee")),
                reporter=_display_name(fields.get("reporter")),
                created_at=_time(fields.get("created") or fields.get("created_at")),
                resolved_at=_opt_time(fields.get("resolutiondate") or fields.get("resolved_at")),
                url=f"{base_url.rstrip('/')}/browse/{key}" if base_url else None,
            )
        )
    return defects


def _as_issue_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
        return [item for item in payload["issues"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(
        "Expected a JIRA search response with an 'issues' array, or a flat list of issues."
    )


def _status_category(fields: dict[str, Any]) -> str:
    status = fields.get("status")
    raw = ""
    if isinstance(status, dict):
        category = status.get("statusCategory")
        if isinstance(category, dict):
            raw = str(category.get("name") or category.get("key") or "")
    raw = (raw or str(fields.get("status_category") or "")).strip().lower()

    if raw in DONE_CATEGORIES:
        return "done"
    if raw in IN_PROGRESS_CATEGORIES:
        return "in_progress"
    if fields.get("resolutiondate") or fields.get("resolved_at"):
        return "done"
    return "todo"


def _severity(fields: dict[str, Any], mapping: FieldMapping) -> str:
    value = _field_value(fields, mapping.severity) or _opt_str(fields.get("severity"))
    if value and value in SEVERITY_ORDER:
        return value
    priority = _name_of(fields.get("priority")) or _opt_str(fields.get("priority"))
    if priority:
        return mapping.severity_from_priority.get(priority, "Unknown")
    return "Unknown"


def _component(fields: dict[str, Any], mapping: FieldMapping) -> str:
    raw = fields.get(mapping.component) or fields.get("component")
    if isinstance(raw, list) and raw:
        first = raw[0]
        return str(first.get("name") if isinstance(first, dict) else first)
    if isinstance(raw, dict):
        return str(raw.get("name") or "Unassigned")
    return str(raw or "Unassigned")


def _found_phase(fields: dict[str, Any], mapping: FieldMapping) -> str:
    value = (
        (_field_value(fields, mapping.found_phase) or _opt_str(fields.get("found_phase")) or "")
        .strip()
        .lower()
    )
    return value if value in PHASE_ORDER else "testing"


def _field_value(fields: dict[str, Any], field_id: str) -> str | None:
    raw = fields.get(field_id)
    if isinstance(raw, dict):
        return _opt_str(raw.get("value") or raw.get("name"))
    return _opt_str(raw)


def _project_of(issue: dict[str, Any], fields: dict[str, Any], key: str) -> str | None:
    project = fields.get("project")
    if isinstance(project, dict):
        return _opt_str(project.get("key") or project.get("name"))
    return _opt_str(issue.get("project")) or (key.split("-")[0] if "-" in key else None)


def _name_of(value: object) -> str | None:
    return _opt_str(value.get("name")) if isinstance(value, dict) else None


def _display_name(value: object) -> str | None:
    if isinstance(value, dict):
        return _opt_str(value.get("displayName") or value.get("name"))
    return _opt_str(value)


def _opt_str(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _time(value: object) -> datetime:
    return _opt_time(value) or datetime.now(UTC).replace(tzinfo=None)


def _opt_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    text = value.replace("Z", "+00:00")
    # JIRA writes +0800 without the colon that fromisoformat wants.
    if len(text) > 5 and (text[-5] in "+-") and ":" not in text[-5:]:
        text = f"{text[:-2]}:{text[-2:]}"
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        return None
