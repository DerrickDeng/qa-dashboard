"""Generate demo data for Playwright reports and agent runs, in the shapes the API ingests.

Defects are not generated here: they come from the local mock JIRA through the
real sync job, so that path gets exercised too.

This exists so a fresh clone has a populated dashboard. Everything it writes is
invented: fictional features and fictional agent runs. Delete
`samples/generated/` and push your own data to replace it.

    python scripts/generate_demo_data.py
"""

from __future__ import annotations

import json
import random
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "samples" / "generated"

DAYS = 21
SEED = 20260912

PROJECTS = ["hk-sit", "hk-uat", "sg-sit", "tw-sit"]
APPLICATION_CODE = "QAD"
PRODUCT_TYPE = "WEB"

# feature -> scenarios, with a behaviour profile per scenario.
#   stable  - passes
#   flaky   - passes most days, fails or retries on others
#   broken  - fails consistently for a stretch, then gets fixed
#   slow    - passes but takes a long time
#   skipped - never runs (test.skip), so every run reports one skipped test
FEATURES: dict[str, list[tuple[str, str]]] = {
    "Login": [
        ("a customer signs in with a valid password", "stable"),
        ("a wrong password shows the error banner", "stable"),
        ("a locked account is refused", "flaky"),
    ],
    "Fund transfer": [
        ("a customer transfers to a saved payee", "stable"),
        ("a transfer above the daily limit is refused", "stable"),
        ("the confirmation SMS code is accepted", "flaky"),
        ("a transfer to a new payee needs approval", "broken"),
    ],
    "Card management": [
        ("a customer freezes a card", "stable"),
        ("a customer sees the last ten transactions", "slow"),
        ("a replacement card can be ordered", "stable"),
    ],
    "Statements": [
        ("a customer downloads a PDF statement", "flaky"),
        ("statement filters narrow the list", "stable"),
        ("a statement can be exported to CSV", "skipped"),
    ],
    "Onboarding": [
        ("a new customer completes identity checks", "slow"),
        ("an expired document is rejected", "stable"),
        ("the address step validates a postcode", "stable"),
    ],
}

ERRORS = {
    "flaky": "TimeoutError: locator.click: Timeout 10000ms exceeded.\n  waiting for getByRole('button', { name: 'Confirm' })",
    "broken": "Error: expect(received).toHaveText(expected)\n\nExpected: \"Pending approval\"\nReceived: \"Submitted\"",
}


AGENTS = ["testcase-agent", "api-agent", "ui-automation-agent"]
MODELS = ["claude-opus-5", "claude-sonnet-5"]
PROMPT_VERSIONS = ["v3", "v4"]


def main() -> None:
    random.seed(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("*"):
        stale.unlink()

    today = date.today()
    days = [today - timedelta(days=offset) for offset in range(DAYS - 1, -1, -1)]

    manifest = {"playwright": [], "agent_runs": "agent-runs.json"}

    for index, day in enumerate(days):
        for project in PROJECTS:
            report = _build_report(day, project, index)
            name = f"playwright-{day.isoformat()}-{project}.json"
            (OUT / name).write_text(json.dumps(report, indent=2), encoding="utf-8")
            region, environment = project.split("-")
            manifest["playwright"].append(
                {
                    "file": name,
                    "application_code": APPLICATION_CODE,
                    "region": region,
                    "environment": environment,
                    "product_type": PRODUCT_TYPE,
                    "job_name": f"QAD-UI-Automation-{project.upper()}",
                    "build_number": str(1200 + index * len(PROJECTS) + PROJECTS.index(project)),
                }
            )

    (OUT / "agent-runs.json").write_text(
        json.dumps(_build_agent_runs(days), indent=2), encoding="utf-8"
    )
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Wrote {len(manifest['playwright'])} Playwright reports and agent runs")
    print(f"  -> {OUT.relative_to(REPO_ROOT)}")


def _outcome(profile: str, day_index: int, project: str) -> tuple[str, int]:
    """Return (playwright outcome, retry count) for one scenario on one day."""
    roll = random.random()

    if profile == "stable":
        return ("unexpected", 0) if roll < 0.01 else ("expected", 0)

    if profile == "slow":
        return ("expected", 0)

    if profile == "skipped":
        return ("skipped", 0)

    if profile == "flaky":
        # Genuinely intermittent: sometimes clean, sometimes a retry rescue,
        # sometimes a hard fail. UAT is the noisier environment.
        threshold = 0.55 if project.endswith("uat") else 0.70
        if roll < threshold:
            return ("expected", 0)
        if roll < threshold + 0.25:
            return ("flaky", 1)
        return ("unexpected", 2)

    if profile == "broken":
        # Broken for the first stretch of the window, fixed after.
        return ("unexpected", 2) if day_index < DAYS - 6 else ("expected", 0)

    return ("expected", 0)


def _build_report(day: date, project: str, day_index: int) -> dict:
    started = datetime.combine(day, time(2, 15)).replace(tzinfo=UTC)
    suites = []
    total_duration = 0

    for feature, scenarios in FEATURES.items():
        specs = []
        for title, profile in scenarios:
            outcome, retries = _outcome(profile, day_index, project)
            base = random.randint(3500, 9000) if profile == "slow" else random.randint(600, 3200)

            results = []
            for attempt in range(retries + 1):
                is_last = attempt == retries
                if outcome == "expected":
                    status = "passed"
                elif outcome == "flaky":
                    status = "passed" if is_last else "failed"
                elif outcome == "skipped":
                    status = "skipped"
                else:
                    status = "failed"

                result = {
                    "workerIndex": 0,
                    "status": status,
                    "duration": base + random.randint(-200, 400),
                    "retry": attempt,
                    "startTime": started.isoformat().replace("+00:00", "Z"),
                    "attachments": [],
                    "errors": [],
                    "stdout": [],
                    "stderr": [],
                }
                if status == "failed":
                    message = ERRORS["broken" if profile == "broken" else "flaky"]
                    result["errors"] = [{"message": message}]
                    result["error"] = {"message": message}
                results.append(result)
                total_duration += result["duration"]

            specs.append(
                {
                    "title": title,
                    "ok": outcome in ("expected", "flaky"),
                    "tags": [f"@{feature.lower().replace(' ', '-')}"],
                    "id": f"{feature}-{title}",
                    "file": f"src/features/{feature.lower().replace(' ', '-')}.feature.spec.js",
                    "line": 6,
                    "column": 7,
                    "tests": [
                        {
                            "timeout": 120000,
                            "annotations": [],
                            "expectedStatus": "passed",
                            "projectName": project,
                            "projectId": project,
                            "results": results,
                            "status": outcome,
                        }
                    ],
                }
            )

        file_name = f"src/features/{feature.lower().replace(' ', '-')}.feature.spec.js"
        suites.append(
            {
                "title": file_name,
                "file": file_name,
                "line": 0,
                "column": 0,
                "specs": [],
                "suites": [
                    {
                        "title": feature,
                        "file": file_name,
                        "line": 4,
                        "column": 1,
                        "specs": specs,
                    }
                ],
            }
        )

    flat = [
        test
        for suite in suites
        for child in suite["suites"]
        for spec in child["specs"]
        for test in spec["tests"]
    ]

    return {
        "config": {
            "rootDir": "/workspace",
            "projects": [{"id": project, "name": project}],
            "version": "1.48.2",
        },
        "suites": suites,
        "errors": [],
        "stats": {
            "startTime": started.isoformat().replace("+00:00", "Z"),
            "duration": total_duration,
            "expected": sum(1 for t in flat if t["status"] == "expected"),
            "skipped": sum(1 for t in flat if t["status"] == "skipped"),
            "unexpected": sum(1 for t in flat if t["status"] == "unexpected"),
            "flaky": sum(1 for t in flat if t["status"] == "flaky"),
        },
    }


def _build_agent_runs(days: list[date]) -> list[dict]:
    runs = []
    for index, day in enumerate(days):
        for agent in AGENTS:
            if random.random() < 0.25:
                continue

            # Later days use the newer prompt, which does better.
            prompt = PROMPT_VERSIONS[1] if index > DAYS - 9 else PROMPT_VERSIONS[0]
            model = random.choice(MODELS)
            quality = 0.82 if prompt == "v4" else 0.68
            if model == "claude-sonnet-5":
                quality -= 0.07

            generated = random.randint(6, 14)
            items = []
            for item_index in range(generated):
                accepted = random.random() < quality
                edited = accepted and random.random() < 0.45
                items.append(
                    {
                        "item_id": f"item-{item_index + 1}",
                        "accepted": accepted,
                        "edited": edited,
                        "edit_distance": random.randint(5, 90) if edited else 0,
                    }
                )

            golden_total = random.randint(7, 12)
            matched = min(golden_total, int(round(golden_total * (quality + random.uniform(-0.08, 0.08)))))
            matched = max(0, matched)
            extra = max(0, generated - matched - random.randint(0, 2))
            hallucinated = random.randint(0, 2) if quality < 0.75 else random.randint(0, 1)

            started = datetime.combine(day, time(random.randint(1, 6), random.randint(0, 59)))
            runs.append(
                {
                    "run_id": f"{agent}-{day.isoformat()}-{random.randint(100, 999)}",
                    "agent": agent,
                    "model": model,
                    "prompt_version": prompt,
                    "started_at": started.isoformat() + "Z",
                    "duration_ms": random.randint(9000, 48000),
                    "input_ref": random.choice(list(FEATURES)),
                    "tokens": {
                        "input": random.randint(4000, 18000),
                        "output": random.randint(900, 4200),
                    },
                    "cost_usd": round(random.uniform(0.01, 0.11), 4),
                    "items": items,
                    "comparison": {
                        "golden_ref": random.choice(list(FEATURES)),
                        "golden_total": golden_total,
                        "matched": matched,
                        "missing": golden_total - matched,
                        "extra": extra,
                        "hallucinated": hallucinated,
                    },
                }
            )
    return runs


if __name__ == "__main__":
    main()
