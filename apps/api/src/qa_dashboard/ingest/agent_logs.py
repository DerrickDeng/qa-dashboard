"""Turn an agent run log into one AgentRun row.

The log is whatever the agent writes after a run plus a review. One JSON object
per run, or an array of them. The contract:

```json
{
  "run_id": "tc-2026-09-11-001",
  "agent": "testcase-agent",
  "model": "claude-opus-5",
  "prompt_version": "v4",
  "started_at": "2026-09-11T02:14:00Z",
  "duration_ms": 18400,
  "input_ref": "LAB-101",
  "tokens": {"input": 7400, "output": 2100},
  "cost_usd": 0.042,

  "items": [
    {"item_id": "s1", "accepted": true,  "edited": false, "edit_distance": 0},
    {"item_id": "s2", "accepted": true,  "edited": true,  "edit_distance": 34},
    {"item_id": "s3", "accepted": false, "edited": false, "edit_distance": 0}
  ],

  "comparison": {
    "golden_ref": "LAB-101",
    "golden_total": 9,
    "matched": 7,
    "missing": 2,
    "extra": 1,
    "hallucinated": 1
  }
}
```

`items` drives adoption and needs a human verdict per produced item.
`comparison` drives accuracy and needs a reviewed Golden set. Either block may
be omitted - the affected metrics then simply have no data for that run, which
is honest, rather than being silently counted as zero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class AgentLogFormatError(ValueError):
    """The payload is not an agent run log."""


@dataclass
class ParsedAgentRun:
    id: str
    agent: str
    model: str
    prompt_version: str
    started_at: datetime
    duration_ms: int
    input_ref: str
    generated: int
    accepted: int
    accepted_unchanged: int
    rejected: int
    edit_distance: int
    golden_total: int
    matched: int
    missing: int
    extra: int
    hallucinated: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


def parse_logs(payload: Any) -> list[ParsedAgentRun]:
    entries = payload if isinstance(payload, list) else [payload]
    if not entries or not all(isinstance(entry, dict) for entry in entries):
        raise AgentLogFormatError("Expected an agent run log object, or an array of them.")
    return [_parse_one(entry) for entry in entries]


def _parse_one(entry: dict[str, Any]) -> ParsedAgentRun:
    run_id = str(entry.get("run_id") or entry.get("id") or "").strip()
    agent = str(entry.get("agent") or "").strip()
    if not run_id or not agent:
        raise AgentLogFormatError("Each agent run log needs a 'run_id' and an 'agent'.")

    items = entry.get("items")
    items = items if isinstance(items, list) else []
    generated = int(entry.get("generated") or len(items))
    accepted = sum(1 for item in items if _truthy(item.get("accepted")))
    unchanged = sum(
        1 for item in items if _truthy(item.get("accepted")) and not _truthy(item.get("edited"))
    )
    edit_distance = sum(int(item.get("edit_distance") or 0) for item in items)

    comparison = entry.get("comparison")
    comparison = comparison if isinstance(comparison, dict) else {}

    tokens = entry.get("tokens")
    tokens = tokens if isinstance(tokens, dict) else {}

    started_at = _time(entry.get("started_at"))

    return ParsedAgentRun(
        id=run_id,
        agent=agent,
        model=str(entry.get("model") or ""),
        prompt_version=str(entry.get("prompt_version") or ""),
        started_at=started_at,
        duration_ms=int(entry.get("duration_ms") or 0),
        input_ref=str(entry.get("input_ref") or comparison.get("golden_ref") or ""),
        generated=generated,
        accepted=accepted,
        accepted_unchanged=unchanged,
        rejected=max(0, generated - accepted),
        edit_distance=edit_distance,
        golden_total=int(comparison.get("golden_total") or 0),
        matched=int(comparison.get("matched") or 0),
        missing=int(comparison.get("missing") or 0),
        extra=int(comparison.get("extra") or 0),
        hallucinated=int(comparison.get("hallucinated") or 0),
        input_tokens=int(tokens.get("input") or 0),
        output_tokens=int(tokens.get("output") or 0),
        cost_usd=float(entry.get("cost_usd") or 0.0),
    )


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _time(value: object) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.now(UTC).replace(tzinfo=None)
