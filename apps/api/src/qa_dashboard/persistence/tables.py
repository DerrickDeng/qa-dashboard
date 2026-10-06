"""Storage schema for the three data sources.

One table per ingested entity, plus a flattened test-result table so the
execution and flaky metrics are plain SQL aggregates rather than JSON walks.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TestRun(Base):
    """One uploaded Playwright JSON report."""

    __tablename__ = "test_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # CI context, mirroring what the Jenkins pipeline already labels a run with.
    application_code: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", index=True
    )
    region: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False, default="", index=True)
    product_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    job_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    build_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ci_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    #: True when the full Playwright HTML report bundle was uploaded with the run,
    #: so "View report" can open the real report with its traces and screenshots.
    has_bundle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flaky: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: The original report, kept so the detail view can render the full tree.
    raw_report: Mapped[str] = mapped_column(Text, nullable=False)


class TestResult(Base):
    """One test within one run, flattened out of the report tree."""

    __tablename__ = "test_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    #: Stable identity across runs: file + full title + project.
    test_key: Mapped[str] = mapped_column(String(600), nullable=False, index=True)
    file: Mapped[str] = mapped_column(String(300), nullable=False)
    suite_path: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    #: Playwright project. In this setup that is the region-environment pair, e.g. "hk-sit".
    project_name: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    #: BDD Feature name, taken from the test's describe path.
    feature: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    #: BDD tags, comma-separated, e.g. "@smoke,@payments".
    tags: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    #: passed | failed | flaky | skipped
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class Defect(Base):
    """One JIRA issue of a bug-like type."""

    __tablename__ = "defects"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    project: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(String(600), nullable=False, default="")
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False, default="Bug")

    status: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    #: todo | in_progress | done - normalised from the JIRA status category.
    status_category: Mapped[str] = mapped_column(String(32), nullable=False, default="todo")

    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="Unknown", index=True)
    priority: Mapped[str | None] = mapped_column(String(32), nullable=True)
    component: Mapped[str] = mapped_column(String(120), nullable=False, default="Unassigned")
    #: Where the defect was found: requirement / development / testing / production.
    found_phase: Mapped[str] = mapped_column(String(32), nullable=False, default="testing")
    root_cause: Mapped[str | None] = mapped_column(String(64), nullable=True)

    assignee: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reporter: Mapped[str | None] = mapped_column(String(120), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AgentRun(Base):
    """One run of a generation agent, with its review outcome."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    run_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: What the agent was asked to work on, e.g. a story id.
    input_ref: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    #: Adoption: how the reviewer treated each generated item.
    generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_unchanged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edit_distance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    #: Accuracy: comparison against the reviewed Golden set.
    golden_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hallucinated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class User(Base):
    """A person who can sign in to the dashboard."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    #: scrypt hash with its salt and cost - never the password itself.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Bumped on a password change or disable, which ends every existing session.
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
