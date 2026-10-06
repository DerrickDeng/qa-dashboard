"""A local stand-in for JIRA's REST API, for development without a real instance.

It implements only what the dashboard's sync job touches, with the same shapes
JIRA returns, so pointing the sync job at a real instance later is a change of
base URL and token - nothing else:

    GET  /rest/api/{2,3}/search          JQL search, startAt/maxResults paging
    GET  /rest/api/{2,3}/field           field list, to look up customfield ids
    POST /rest/api/{2,3}/issue           create an issue (to simulate a new bug)
    POST /rest/api/{2,3}/issue/{key}/transitions   move an issue to Done
    GET  /browse/{key}                   a tiny page, so issue links resolve

Everything is fictional and regenerated on start, relative to today.

JQL is a small subset. An unsupported clause is refused with 400, the way JIRA
refuses bad JQL, instead of being silently ignored:

    project = KEY            project in (A, B)
    issuetype = Bug          issuetype in (Bug, Defect)
    created >= -30d          created >= "2026-09-01"      (also updated, <=)
    status = "In Progress"   statusCategory = Done
    ... joined by AND, optionally followed by ORDER BY created|updated ASC|DESC

Auth mirrors the two JIRA flavours: Basic (email + API token, Cloud) or Bearer
(personal access token, Data Center). The accepted token is MOCK_JIRA_TOKEN.

    uvicorn mock_jira:app --port 8002
"""

from __future__ import annotations

import base64
import html
import os
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

TOKEN = os.environ.get("MOCK_JIRA_TOKEN", "mock-token")
SEED = int(os.environ.get("MOCK_JIRA_SEED", "20260913"))
HISTORY_DAYS = 60
MAX_RESULTS_CAP = 100

#: Real JIRA uses opaque customfield ids. These mimic that on purpose, so the
#: dashboard's field-mapping file is exercised the same way it will be for real.
SEVERITY_FIELD = "customfield_10050"
FOUND_PHASE_FIELD = "customfield_10051"
ROOT_CAUSE_FIELD = "customfield_10052"

FIELDS = [
    {"id": "summary", "name": "Summary", "custom": False},
    {"id": "issuetype", "name": "Issue Type", "custom": False},
    {"id": "status", "name": "Status", "custom": False},
    {"id": "priority", "name": "Priority", "custom": False},
    {"id": "components", "name": "Component/s", "custom": False},
    {"id": "created", "name": "Created", "custom": False},
    {"id": "resolutiondate", "name": "Resolved", "custom": False},
    {"id": "assignee", "name": "Assignee", "custom": False},
    {"id": "reporter", "name": "Reporter", "custom": False},
    {"id": SEVERITY_FIELD, "name": "Severity", "custom": True},
    {"id": FOUND_PHASE_FIELD, "name": "Found In Phase", "custom": True},
    {"id": ROOT_CAUSE_FIELD, "name": "Root Cause", "custom": True},
    {"id": "customfield_10020", "name": "Sprint", "custom": True},
]

PROJECTS = {"QAD": "QA Dashboard", "SHOP": "Online Store"}
COMPONENTS = ["Login", "Fund transfer", "Card management", "Statements", "Onboarding"]
SEVERITIES = ["Blocker", "Critical", "Major", "Minor", "Trivial"]
SEVERITY_WEIGHTS = [3, 12, 40, 33, 12]
PRIORITY_OF = {
    "Blocker": "Highest",
    "Critical": "High",
    "Major": "Medium",
    "Minor": "Low",
    "Trivial": "Lowest",
}
PHASES = ["development", "testing", "staging", "production"]
PHASE_WEIGHTS = [18, 58, 16, 8]
ROOT_CAUSES = [
    "Code defect",
    "Missed requirement",
    "Environment",
    "Test data",
    "Third-party API",
    "Configuration",
]
PEOPLE = ["Chen Wei", "Lim Hui", "Rajesh K", "Wong Ka Yan", "Tan Boon"]
SUBJECTS = [
    "Transfer confirmation page",
    "Login error banner",
    "Card freeze toggle",
    "Statement download",
    "Onboarding identity check",
    "Payee management",
]
PROBLEMS = [
    "shows the wrong amount",
    "times out intermittently",
    "does not respond",
    "has untranslated text",
    "validates inconsistently",
    "does not refresh its status",
]

#: The Authorization header. Declared at module level on purpose: with postponed
#: annotations FastAPI resolves this name from module globals, and a local alias
#: silently turns the header into a query parameter.
Auth = Annotated[str | None, Header()]

STATUS_CATEGORY = {"Open": "To Do", "In Progress": "In Progress", "Closed": "Done"}
DONE_TRANSITION_ID = "31"


@dataclass
class Issue:
    key: str
    project: str
    issue_type: str
    summary: str
    status: str
    priority: str
    component: str
    severity: str | None
    found_phase: str | None
    root_cause: str | None
    assignee: str
    reporter: str
    created: datetime
    updated: datetime
    resolved: datetime | None

    def to_json(self) -> dict[str, Any]:
        stamp = "%Y-%m-%dT%H:%M:%S.000+0800"
        return {
            "id": str(abs(hash(self.key)) % 10_000_000),
            "key": self.key,
            "self": f"/rest/api/2/issue/{self.key}",
            "fields": {
                "project": {"key": self.project, "name": PROJECTS.get(self.project, self.project)},
                "summary": self.summary,
                "issuetype": {"name": self.issue_type},
                "status": {
                    "name": self.status,
                    "statusCategory": {"name": STATUS_CATEGORY.get(self.status, "To Do")},
                },
                "priority": {"name": self.priority},
                "components": [{"name": self.component}],
                SEVERITY_FIELD: {"value": self.severity} if self.severity else None,
                FOUND_PHASE_FIELD: {"value": self.found_phase} if self.found_phase else None,
                ROOT_CAUSE_FIELD: {"value": self.root_cause} if self.root_cause else None,
                "assignee": {"displayName": self.assignee},
                "reporter": {"displayName": self.reporter},
                "created": self.created.strftime(stamp),
                "updated": self.updated.strftime(stamp),
                "resolutiondate": self.resolved.strftime(stamp) if self.resolved else None,
            },
        }


class Store:
    def __init__(self, today: date | None = None, seed: int = SEED) -> None:
        self.today = today or date.today()
        self.issues: dict[str, Issue] = {}
        self.counters = {project: 4100 for project in PROJECTS}
        self._generate(random.Random(seed))

    def _next_key(self, project: str) -> str:
        self.counters[project] += 1
        return f"{project}-{self.counters[project]}"

    def _generate(self, rng: random.Random) -> None:
        now = datetime.combine(self.today, time(18, 0))
        for offset in range(HISTORY_DAYS - 1, -1, -1):
            day = self.today - timedelta(days=offset)
            for project in PROJECTS:
                # Mostly bugs, plus stories and tasks so the issue-type filter matters.
                for _ in range(rng.randint(0, 4) if project == "QAD" else rng.randint(0, 2)):
                    issue_type = rng.choices(["Bug", "Story", "Task"], [70, 20, 10])[0]
                    severity = rng.choices(SEVERITIES, SEVERITY_WEIGHTS)[0]
                    created = datetime.combine(day, time(rng.randint(9, 17), rng.randint(0, 59)))

                    status, resolved = "Open", None
                    fix_days = {
                        "Blocker": 1,
                        "Critical": 2,
                        "Major": 5,
                        "Minor": 11,
                        "Trivial": 20,
                    }[severity]
                    if rng.random() < 0.72:
                        candidate = created + timedelta(
                            days=max(0.2, rng.gauss(fix_days, fix_days / 2))
                        )
                        if candidate <= now:
                            status, resolved = "Closed", candidate
                    if resolved is None and rng.random() < 0.4:
                        status = "In Progress"

                    # About one bug in ten was filed without the custom fields filled in,
                    # which real instances are full of.
                    sparse = rng.random() < 0.1
                    is_bug = issue_type == "Bug"
                    key = self._next_key(project)
                    self.issues[key] = Issue(
                        key=key,
                        project=project,
                        issue_type=issue_type,
                        summary=f"{rng.choice(SUBJECTS)} {rng.choice(PROBLEMS)}",
                        status=status,
                        priority=PRIORITY_OF[severity],
                        component=rng.choice(COMPONENTS),
                        severity=None if (sparse or not is_bug) else severity,
                        found_phase=None
                        if (sparse or not is_bug)
                        else rng.choices(PHASES, PHASE_WEIGHTS)[0],
                        root_cause=None if (sparse or not is_bug) else rng.choice(ROOT_CAUSES),
                        assignee=rng.choice(PEOPLE),
                        reporter=rng.choice(PEOPLE),
                        created=created,
                        updated=resolved or created,
                        resolved=resolved,
                    )


# --- JQL subset -------------------------------------------------------------

_ORDER = re.compile(r"\s+ORDER\s+BY\s+(created|updated)(?:\s+(ASC|DESC))?\s*$", re.IGNORECASE)
_IN = re.compile(r"^(project|issuetype|status)\s+in\s*\((.+)\)$", re.IGNORECASE)
_EQ = re.compile(r"^(project|issuetype|status|statusCategory)\s*=\s*(.+)$", re.IGNORECASE)
_DATE = re.compile(r"^(created|updated)\s*(>=|<=|>|<)\s*(.+)$", re.IGNORECASE)
_RELATIVE = re.compile(r"^-(\d+)([dw])$", re.IGNORECASE)


class JqlError(ValueError):
    pass


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _date_bound(raw: str, today: date) -> datetime:
    raw = _unquote(raw)
    relative = _RELATIVE.match(raw)
    if relative:
        amount = int(relative.group(1)) * (7 if relative.group(2).lower() == "w" else 1)
        return datetime.combine(today - timedelta(days=amount), time.min)
    try:
        return datetime.fromisoformat(raw)
    except ValueError as error:
        raise JqlError(f"Unsupported date value in JQL: {raw!r}") from error


def run_jql(store: Store, jql: str) -> list[Issue]:
    text = (jql or "").strip()
    order_field, descending = "created", True
    order = _ORDER.search(text)
    if order:
        order_field = order.group(1).lower()
        descending = (order.group(2) or "ASC").upper() == "DESC"
        text = text[: order.start()].strip()
    elif re.match(r"^ORDER\s+BY", text, re.IGNORECASE):
        match = _ORDER.search(" " + text)
        if match:
            order_field = match.group(1).lower()
            descending = (match.group(2) or "ASC").upper() == "DESC"
        text = ""

    predicates = []
    for clause in [
        part.strip() for part in re.split(r"\s+AND\s+", text, flags=re.IGNORECASE) if part.strip()
    ]:
        predicates.append(_predicate(clause, store.today))

    results = [issue for issue in store.issues.values() if all(test(issue) for test in predicates)]
    results.sort(key=lambda issue: getattr(issue, order_field), reverse=descending)
    return results


def _predicate(clause: str, today: date):  # type: ignore[no-untyped-def]
    attribute = {"project": "project", "issuetype": "issue_type", "status": "status"}

    match = _IN.match(clause)
    if match:
        name = match.group(1).lower()
        wanted = {_unquote(item).lower() for item in match.group(2).split(",")}
        return lambda issue: str(getattr(issue, attribute[name])).lower() in wanted

    match = _DATE.match(clause)
    if match:
        field_name, operator, bound = (
            match.group(1).lower(),
            match.group(2),
            _date_bound(match.group(3), today),
        )
        comparisons = {
            ">=": lambda value: value >= bound,
            "<=": lambda value: value <= bound,
            ">": lambda value: value > bound,
            "<": lambda value: value < bound,
        }
        return lambda issue: comparisons[operator](getattr(issue, field_name))

    match = _EQ.match(clause)
    if match:
        name, value = match.group(1).lower(), _unquote(match.group(2)).lower()
        if name == "statuscategory":
            return lambda issue: STATUS_CATEGORY.get(issue.status, "To Do").lower() == value
        return lambda issue: str(getattr(issue, attribute[name])).lower() == value

    raise JqlError(
        f"The mock does not support this JQL clause: {clause!r}. "
        "Supported: project/issuetype/status = or in (...), statusCategory =, "
        "created/updated with >= <= > < and -Nd or a date, joined by AND, "
        "optionally ORDER BY created|updated ASC|DESC."
    )


# --- HTTP -------------------------------------------------------------------


def create_app(store: Store | None = None) -> FastAPI:
    app = FastAPI(title="Mock JIRA", version="0.1.0", description=__doc__)
    app.state.store = store or Store()

    def require_auth(authorization: str | None) -> None:
        if not authorization:
            raise HTTPException(status_code=401, detail="Authentication required.")
        scheme, _, credential = authorization.partition(" ")
        if scheme.lower() == "bearer" and credential == TOKEN:
            return
        if scheme.lower() == "basic":
            try:
                _, _, secret = base64.b64decode(credential).decode("utf-8").partition(":")
            except ValueError:
                secret = ""
            if secret == TOKEN:
                return
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    @app.get("/rest/api/{version}/search")
    def search(
        request: Request,
        version: str,
        authorization: Auth = None,
        jql: str = "",
        start_at: Annotated[int, Query(alias="startAt", ge=0)] = 0,
        max_results: Annotated[int, Query(alias="maxResults", ge=0)] = 50,
    ) -> dict[str, Any]:
        _check_version(version)
        require_auth(authorization)
        try:
            matched = run_jql(request.app.state.store, jql)
        except JqlError as error:
            # JIRA answers bad JQL with 400 and an errorMessages array.
            raise HTTPException(status_code=400, detail={"errorMessages": [str(error)]}) from error

        size = min(max_results, MAX_RESULTS_CAP)
        page = matched[start_at : start_at + size]
        return {
            "startAt": start_at,
            "maxResults": size,
            "total": len(matched),
            "issues": [issue.to_json() for issue in page],
        }

    @app.get("/rest/api/{version}/field")
    def fields(version: str, authorization: Auth = None) -> list[dict[str, Any]]:
        _check_version(version)
        require_auth(authorization)
        return FIELDS

    @app.post("/rest/api/{version}/issue", status_code=201)
    async def create_issue(
        request: Request, version: str, authorization: Auth = None
    ) -> dict[str, Any]:
        _check_version(version)
        require_auth(authorization)
        body = await request.json()
        fields_in = body.get("fields") or {}
        project = str((fields_in.get("project") or {}).get("key") or "QAD")
        if project not in PROJECTS:
            raise HTTPException(status_code=400, detail={"errors": {"project": "Unknown project."}})

        state: Store = request.app.state.store
        now = datetime.now().replace(microsecond=0)
        key = state._next_key(project)
        severity = (fields_in.get(SEVERITY_FIELD) or {}).get("value")
        state.issues[key] = Issue(
            key=key,
            project=project,
            issue_type=str((fields_in.get("issuetype") or {}).get("name") or "Bug"),
            summary=str(fields_in.get("summary") or "(no summary)"),
            status="Open",
            priority=str(
                (fields_in.get("priority") or {}).get("name")
                or PRIORITY_OF.get(severity or "", "Medium")
            ),
            component=str(((fields_in.get("components") or [{}])[0]).get("name") or "Unassigned"),
            severity=severity,
            found_phase=(fields_in.get(FOUND_PHASE_FIELD) or {}).get("value"),
            root_cause=(fields_in.get(ROOT_CAUSE_FIELD) or {}).get("value"),
            assignee=str((fields_in.get("assignee") or {}).get("displayName") or "Unassigned"),
            reporter=str((fields_in.get("reporter") or {}).get("displayName") or "Mock User"),
            created=now,
            updated=now,
            resolved=None,
        )
        return {"id": key, "key": key, "self": f"/rest/api/{version}/issue/{key}"}

    @app.post("/rest/api/{version}/issue/{key}/transitions", status_code=204)
    async def transition(
        request: Request, version: str, key: str, authorization: Auth = None
    ) -> None:
        _check_version(version)
        require_auth(authorization)
        state: Store = request.app.state.store
        issue = state.issues.get(key)
        if issue is None:
            raise HTTPException(
                status_code=404, detail={"errorMessages": ["Issue does not exist."]}
            )
        body = await request.json()
        transition_id = str((body.get("transition") or {}).get("id") or "")
        if transition_id != DONE_TRANSITION_ID:
            raise HTTPException(
                status_code=400,
                detail={
                    "errorMessages": [
                        f"The mock supports transition id {DONE_TRANSITION_ID} (Done)."
                    ]
                },
            )
        now = datetime.now().replace(microsecond=0)
        issue.status, issue.resolved, issue.updated = "Closed", now, now

    @app.get("/browse/{key}", response_class=HTMLResponse)
    def browse(request: Request, key: str) -> str:
        issue = request.app.state.store.issues.get(key)
        if issue is None:
            raise HTTPException(status_code=404, detail="Issue does not exist.")
        rows = "".join(
            f"<tr><th>{html.escape(label)}</th><td>{html.escape(str(value or '—'))}</td></tr>"
            for label, value in [
                ("Type", issue.issue_type),
                ("Status", issue.status),
                ("Severity", issue.severity),
                ("Priority", issue.priority),
                ("Component", issue.component),
                ("Found in", issue.found_phase),
                ("Root cause", issue.root_cause),
                ("Assignee", issue.assignee),
                ("Created", issue.created),
                ("Resolved", issue.resolved),
            ]
        )
        return (
            "<!doctype html><meta charset='utf-8'><title>" + html.escape(key) + "</title>"
            "<body style='font-family:system-ui;max-width:40rem;margin:2rem auto'>"
            "<p style='color:#888'>Mock JIRA — fictional data</p>"
            f"<h1>{html.escape(key)}: {html.escape(issue.summary)}</h1>"
            f"<table cellpadding='6'>{rows}</table></body>"
        )

    @app.get("/health")
    def health(request: Request) -> dict[str, Any]:
        return {"status": "ok", "issues": len(request.app.state.store.issues)}

    return app


def _check_version(version: str) -> None:
    if version not in {"2", "3"}:
        raise HTTPException(status_code=404, detail="Unknown API version.")


app = create_app()
