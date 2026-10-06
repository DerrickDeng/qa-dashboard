"""The endpoints CI actually calls."""

from __future__ import annotations

import io
import json
import zipfile

from fastapi.testclient import TestClient

from tests.test_playwright_parser import html_report_json, json_reporter_report


def post_report(client: TestClient, report: dict, **form: str):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/ingest/playwright",
        files={"report": ("report.json", json.dumps(report), "application/json")},
        data={
            "application_code": "QAD",
            "region": "hk",
            "environment": "sit",
            **form,
        },
    )


def test_health_reports_jira_mode(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["jira_live"] is False


def test_a_json_report_is_ingested(client: TestClient) -> None:
    response = post_report(client, json_reporter_report())
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["passed"] == 1
    assert body["flaky"] == 1
    assert body["bundle_stored"] is False


def test_re_posting_the_same_report_does_not_double_count(client: TestClient) -> None:
    post_report(client, json_reporter_report())
    post_report(client, json_reporter_report())
    summary = client.get("/api/v1/execution?days=180").json()["summary"]
    assert summary["runs"] == 1
    assert summary["total"] == 2


def test_an_html_index_is_accepted_and_the_zip_is_unpacked(client: TestClient) -> None:
    """CI can push index.html plus the zipped report folder, with no config change."""
    import base64

    payload = json.dumps(html_report_json()).encode()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle_zip:
        bundle_zip.writestr("report.json", payload)
    encoded = base64.b64encode(archive.getvalue()).decode()
    html = (
        "<!doctype html><html><body><script>"
        f'"data:application/zip;base64,{encoded}"'
        "</script></body></html>"
    )

    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as bundle_zip:
        bundle_zip.writestr("playwright-html/index.html", html)

    response = client.post(
        "/api/v1/ingest/playwright",
        files={
            "report": ("index.html", html, "text/html"),
            "bundle": ("playwright-html.zip", outer.getvalue(), "application/zip"),
        },
        data={"application_code": "QAD", "region": "hk", "environment": "sit"},
    )
    assert response.status_code == 200
    assert response.json()["bundle_stored"] is True

    run_id = response.json()["run_id"]
    detail = client.get(f"/api/v1/runs/{run_id}").json()
    assert detail["has_bundle"] is True
    assert detail["bundle_url"] == f"/reports/{run_id}/playwright-html/index.html"


def test_a_bundle_with_a_path_traversal_entry_is_refused(client: TestClient) -> None:
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as bundle_zip:
        bundle_zip.writestr("../../escaped.html", "nope")

    response = client.post(
        "/api/v1/ingest/playwright",
        files={
            "report": ("report.json", json.dumps(json_reporter_report()), "application/json"),
            "bundle": ("bundle.zip", outer.getvalue(), "application/zip"),
        },
        data={"application_code": "QAD"},
    )
    assert response.status_code == 422
    assert "unsafe path" in response.json()["detail"]


def test_a_report_that_is_not_playwright_is_refused(client: TestClient) -> None:
    response = post_report(client, {"totally": "wrong"})
    assert response.status_code == 422
    assert "Unrecognised Playwright report" in response.json()["detail"]


def test_invalid_json_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ingest/playwright",
        files={"report": ("report.json", "{not json", "application/json")},
        data={"application_code": "QAD"},
    )
    assert response.status_code == 422


def test_ci_dimensions_are_stored_and_offered_as_filters(client: TestClient) -> None:
    post_report(client, json_reporter_report(), region="sg", environment="uat", build_number="42")
    filters = client.get("/api/v1/filters").json()
    assert "QAD" in filters["application_codes"]
    assert "sg" in filters["regions"]
    assert "uat" in filters["environments"]


def test_the_region_filter_narrows_the_execution_section(client: TestClient) -> None:
    post_report(client, json_reporter_report(), region="hk")
    other = json_reporter_report()
    other["suites"][0]["suites"][0]["specs"][0]["title"] = "a different scenario"
    post_report(client, other, region="sg")

    hk_only = client.get("/api/v1/execution?days=180&region=hk").json()
    assert hk_only["summary"]["runs"] == 1
    both = client.get("/api/v1/execution?days=180").json()
    assert both["summary"]["runs"] == 2


def test_jira_issues_are_imported_and_classified(client: TestClient) -> None:
    from tests.test_jira_adapter import rest_issue

    response = client.post(
        "/api/v1/ingest/jira",
        files={
            "issues": ("issues.json", json.dumps({"issues": [rest_issue()]}), "application/json")
        },
        data={"replace": "true"},
    )
    assert response.json() == {"imported": 1}

    section = client.get("/api/v1/defects?days=180").json()
    assert section["summary"]["total"] == 1
    assert {row["name"] for row in section["by_severity"]} == {"Critical"}
    assert section["summary"]["escape_rate"] == 1.0


def test_agent_runs_are_imported_with_adoption_and_accuracy(client: TestClient) -> None:
    from tests.test_agent_logs import log

    response = client.post(
        "/api/v1/ingest/agent-runs",
        files={"logs": ("logs.json", json.dumps([log()]), "application/json")},
    )
    assert response.json() == {"imported": 1}

    summary = client.get("/api/v1/ai?days=180").json()["summary"]
    assert summary["generated"] == 3
    assert summary["accepted"] == 2
    assert summary["adoption"] == round(2 / 3, 4)
    assert summary["adoption_unchanged"] == round(1 / 3, 4)
    assert summary["precision"] == round(7 / 8, 4)
    assert summary["recall"] == round(7 / 9, 4)


def test_re_importing_an_agent_run_replaces_it(client: TestClient) -> None:
    from tests.test_agent_logs import log

    for _ in range(2):
        client.post(
            "/api/v1/ingest/agent-runs",
            files={"logs": ("logs.json", json.dumps([log()]), "application/json")},
        )
    assert client.get("/api/v1/ai?days=180").json()["summary"]["runs"] == 1


def test_an_unknown_run_is_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/runs/nope").status_code == 404


def test_empty_sections_do_not_error(client: TestClient) -> None:
    assert client.get("/api/v1/execution").json()["summary"]["runs"] == 0
    assert client.get("/api/v1/defects").json()["summary"]["total"] == 0
    assert client.get("/api/v1/ai").json()["summary"]["runs"] == 0


def bundle_with(name: str, content: str) -> bytes:
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as bundle_zip:
        bundle_zip.writestr(name, content)
    return outer.getvalue()


def test_re_uploading_a_bundle_replaces_the_previous_one(client: TestClient) -> None:
    """A second push of the same run must refresh the report, not keep a stale one."""
    for content in ("<html>first</html>", "<html>second</html>"):
        response = client.post(
            "/api/v1/ingest/playwright",
            files={
                "report": ("report.json", json.dumps(json_reporter_report()), "application/json"),
                "bundle": ("bundle.zip", bundle_with("index.html", content), "application/zip"),
            },
            data={"application_code": "QAD"},
        )
        assert response.json()["bundle_stored"] is True

    run_id = response.json()["run_id"]
    served = client.get(f"/reports/{run_id}/index.html")
    assert served.text == "<html>second</html>"


def test_an_unsafe_path_is_refused_even_when_the_run_was_uploaded_before(
    client: TestClient,
) -> None:
    """The early-exit on an existing directory used to skip validation entirely."""
    client.post(
        "/api/v1/ingest/playwright",
        files={
            "report": ("report.json", json.dumps(json_reporter_report()), "application/json"),
            "bundle": ("bundle.zip", bundle_with("index.html", "ok"), "application/zip"),
        },
        data={"application_code": "QAD"},
    )
    response = client.post(
        "/api/v1/ingest/playwright",
        files={
            "report": ("report.json", json.dumps(json_reporter_report()), "application/json"),
            "bundle": ("bundle.zip", bundle_with("../../escaped.html", "nope"), "application/zip"),
        },
        data={"application_code": "QAD"},
    )
    assert response.status_code == 422


def test_region_and_environment_come_from_the_project_when_not_sent(client: TestClient) -> None:
    """Pushing from a laptop, nobody passes region/env; the hk-sit project says it."""
    response = client.post(
        "/api/v1/ingest/playwright",
        files={"report": ("report.json", json.dumps(json_reporter_report()), "application/json")},
    )
    assert (response.json()["region"], response.json()["environment"]) == ("hk", "sit")
    filters = client.get("/api/v1/filters").json()
    assert filters["regions"] == ["hk"]
    assert filters["environments"] == ["sit"]


def test_explicit_region_and_environment_win_over_the_project(client: TestClient) -> None:
    response = post_report(client, json_reporter_report(), region="tw", environment="uat")
    assert (response.json()["region"], response.json()["environment"]) == ("tw", "uat")


def test_jira_links_point_at_the_instance_they_came_from(client: TestClient) -> None:
    from tests.test_jira_adapter import rest_issue

    client.post(
        "/api/v1/ingest/jira",
        files={"issues": ("i.json", json.dumps({"issues": [rest_issue()]}), "application/json")},
        data={"replace": "true", "browse_base_url": "http://127.0.0.1:8002"},
    )
    recent = client.get("/api/v1/defects?days=180").json()["recent"]
    assert recent[0]["url"] == "http://127.0.0.1:8002/browse/QAD-4101"
