"""Sync defects from JIRA into the dashboard.

Against the local mock JIRA (started by `make up`):

    python scripts/sync_jira.py --mock

Against a real instance, set the environment and drop --mock:

    export QA_JIRA_BASE_URL=https://jira.your-company.com
    export QA_JIRA_API_TOKEN=...     # personal access token (Data Center)
    export QA_JIRA_EMAIL=...         # only for Jira Cloud: email + API token
    export QA_JIRA_API_VERSION=2     # 2 for Data Center; see jira_client.py for Cloud
    export QA_JIRA_JQL='project = QAD AND issuetype = Bug AND created >= -90d'
    python scripts/sync_jira.py

The JIRA token is used only for the JIRA request. It is not stored, not sent to
the dashboard, and not printed.

The push to the dashboard sends the ingest token from QA_INGEST_TOKEN, or from
.env when that is unset; `make setup` creates it.

Run it from apps/api so it uses that Python environment:

    cd apps/api && uv run python ../../scripts/sync_jira.py --mock
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api" / "src"))

from qa_dashboard.ingest.jira import FieldMapping, parse_issues  # noqa: E402
from qa_dashboard.ingest.jira_client import JiraConnection, JiraError, fetch_issues  # noqa: E402

MOCK_BASE_URL = "http://127.0.0.1:8002"
MOCK_TOKEN = "mock-token"
DEFAULT_JQL = "issuetype in (Bug, Defect) AND created >= -90d ORDER BY created DESC"
MAPPING_PATH = REPO_ROOT / "samples" / "jira" / "field-mapping.json"


def ingest_token() -> str:
    """The dashboard ingest token: the environment first, then the repository .env."""
    token = os.environ.get("QA_INGEST_TOKEN", "")
    env_file = REPO_ROOT / ".env"
    if not token and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "QA_INGEST_TOKEN":
                token = value.strip()
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync JIRA defects into the QA dashboard.")
    parser.add_argument("--mock", action="store_true", help="use the local mock JIRA on :8002")
    parser.add_argument("--jql", default=os.environ.get("QA_JIRA_JQL", DEFAULT_JQL))
    parser.add_argument(
        "--dashboard", default=os.environ.get("QA_API_BASE_URL", "http://127.0.0.1:8001")
    )
    args = parser.parse_args()

    token = ingest_token()
    if not token:
        print(
            "ERROR: no ingest token for the dashboard. Run: make setup   (or set QA_INGEST_TOKEN)",
            file=sys.stderr,
        )
        return 2

    if args.mock:
        connection = JiraConnection(
            base_url=os.environ.get("MOCK_JIRA_BASE_URL", MOCK_BASE_URL),
            token=os.environ.get("MOCK_JIRA_TOKEN", MOCK_TOKEN),
        )
    else:
        base_url = os.environ.get("QA_JIRA_BASE_URL", "")
        token = os.environ.get("QA_JIRA_API_TOKEN", "")
        if not (base_url and token):
            print(
                "ERROR: set QA_JIRA_BASE_URL and QA_JIRA_API_TOKEN, "
                "or pass --mock to use the local mock JIRA.",
                file=sys.stderr,
            )
            return 2
        connection = JiraConnection(
            base_url=base_url,
            token=token,
            email=os.environ.get("QA_JIRA_EMAIL", ""),
            api_version=os.environ.get("QA_JIRA_API_VERSION", "2"),
        )

    print(f"JIRA   {connection.search_url}")
    print(f"JQL    {args.jql}")

    try:
        with httpx.Client(timeout=60.0) as client:
            issues = fetch_issues(
                client,
                connection,
                args.jql,
                on_page=lambda fetched, total: print(f"  fetched {fetched} / {total}"),
            )
    except httpx.ConnectError:
        hint = " Start it with: make up" if args.mock else ""
        print(f"ERROR: cannot reach {connection.base_url}.{hint}", file=sys.stderr)
        return 1
    except JiraError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    mapping = FieldMapping.load(MAPPING_PATH)
    defects = parse_issues({"issues": issues}, mapping)
    unknown_severity = sum(1 for item in defects if item.severity == "Unknown")
    print(f"Matched {len(defects)} defects out of {len(issues)} issues.")
    if defects and unknown_severity == len(defects):
        print(
            "WARNING: no defect has a recognised severity. The severity field id in "
            f"{MAPPING_PATH.relative_to(REPO_ROOT)} probably does not match this JIRA."
        )

    try:
        response = httpx.post(
            f"{args.dashboard}/api/v1/ingest/jira",
            files={
                "issues": ("issues.json", json.dumps({"issues": issues}), "application/json")
            },
            data={"replace": "true", "browse_base_url": connection.base_url},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0,
        )
    except httpx.HTTPError as error:
        print(f"ERROR: cannot reach the dashboard at {args.dashboard}: {error}", file=sys.stderr)
        return 1
    if response.status_code != 200:
        print(
            f"ERROR: the dashboard answered {response.status_code}: {response.text}",
            file=sys.stderr,
        )
        return 1

    print(f"Dashboard imported {response.json()['imported']} defects.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
