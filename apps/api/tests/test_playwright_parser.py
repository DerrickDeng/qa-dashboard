"""The parser is the contract with CI, so both accepted report shapes are pinned here."""

from __future__ import annotations

from typing import Any

import pytest

from qa_dashboard.ingest.playwright import ReportFormatError, parse_report


def json_reporter_report(**overrides: Any) -> dict[str, Any]:
    """Minimal but structurally faithful `--reporter=json` output."""
    return {
        "config": {"projects": [{"name": "hk-sit"}]},
        "suites": [
            {
                # The file-level suite: its title IS the file.
                "title": "src/features/login.feature.spec.js",
                "file": "src/features/login.feature.spec.js",
                "specs": [],
                "suites": [
                    {
                        # A describe block, which under playwright-bdd is the Feature.
                        "title": "Login",
                        "file": "src/features/login.feature.spec.js",
                        "specs": [
                            {
                                "title": "a customer signs in",
                                "ok": True,
                                "tags": ["@smoke"],
                                "file": "src/features/login.feature.spec.js",
                                "tests": [
                                    {
                                        "projectName": "hk-sit",
                                        "status": "expected",
                                        "results": [{"duration": 1200, "errors": []}],
                                    }
                                ],
                            },
                            {
                                "title": "a locked account is refused",
                                "ok": False,
                                "tags": ["@smoke"],
                                "file": "src/features/login.feature.spec.js",
                                "tests": [
                                    {
                                        "projectName": "hk-sit",
                                        "status": "flaky",
                                        "results": [
                                            {
                                                "duration": 900,
                                                "errors": [{"message": "TimeoutError: click"}],
                                            },
                                            {"duration": 800, "errors": []},
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
        "errors": [],
        "stats": {
            "startTime": "2026-09-11T02:15:00.000Z",
            "duration": 2900,
            "expected": 1,
            "unexpected": 0,
            "flaky": 1,
            "skipped": 0,
            **overrides,
        },
    }


def html_report_json() -> dict[str, Any]:
    """The HTML reporter's internal report.json, as found inside index.html."""
    return {
        "startTime": 1787049477316,
        "duration": 3922.866,
        "files": [
            {
                "fileId": "abc123",
                "fileName": "tests/.features-gen/hk-sit/src/features/login.feature.spec.js",
                "tests": [
                    {
                        "testId": "t1",
                        "title": "Complete both stages in one block",
                        "projectName": "hk-sit",
                        "duration": 1375,
                        "tags": ["@skill-eval"],
                        "outcome": "expected",
                        "path": ["Skill eval — unbroken TODO block"],
                        "ok": True,
                        "results": [{"status": "passed", "duration": 1375, "errors": []}],
                    }
                ],
                "stats": {"total": 1, "expected": 1, "unexpected": 0, "flaky": 0, "skipped": 0},
            }
        ],
        "projectNames": ["hk-sit"],
        "stats": {"total": 1, "expected": 1, "unexpected": 0, "flaky": 0, "skipped": 0},
    }


# --- Shape A ---------------------------------------------------------------


def test_json_reporter_counts_each_outcome() -> None:
    run = parse_report(json_reporter_report())
    assert run.total == 2
    assert run.count("passed") == 1
    assert run.count("flaky") == 1
    assert run.count("failed") == 0


def test_json_reporter_keeps_the_describe_title_as_the_feature() -> None:
    run = parse_report(json_reporter_report())
    assert {item.feature for item in run.results} == {"Login"}


def test_the_file_level_suite_is_not_part_of_the_feature_path() -> None:
    """Regression: every suite carries `file`, so only title == file marks the file suite."""
    run = parse_report(json_reporter_report())
    assert all(".spec.js" not in item.feature for item in run.results)


def test_json_reporter_keeps_bdd_tags() -> None:
    run = parse_report(json_reporter_report())
    assert {item.tags for item in run.results} == {"@smoke"}


def test_a_flaky_test_records_its_retry_and_first_error() -> None:
    run = parse_report(json_reporter_report())
    flaky = next(item for item in run.results if item.status == "flaky")
    assert flaky.retries == 1
    assert flaky.error_message is not None
    assert "TimeoutError" in flaky.error_message


def test_project_name_is_carried_through() -> None:
    run = parse_report(json_reporter_report())
    assert {item.project_name for item in run.results} == {"hk-sit"}


def test_a_test_without_a_describe_block_has_no_feature() -> None:
    report = json_reporter_report()
    suite = report["suites"][0]
    suite["specs"] = suite["suites"][0]["specs"]
    suite["suites"] = []
    run = parse_report(report)
    assert {item.feature for item in run.results} == {""}


# --- Shape B ---------------------------------------------------------------


def test_html_report_json_is_accepted() -> None:
    run = parse_report(html_report_json())
    assert run.total == 1
    assert run.count("passed") == 1


def test_html_report_json_uses_path_as_the_feature_and_epoch_millis_for_time() -> None:
    run = parse_report(html_report_json())
    assert run.results[0].feature == "Skill eval — unbroken TODO block"
    assert run.results[0].tags == "@skill-eval"
    assert run.started_at.year == 2026


# --- Identity and errors ---------------------------------------------------


def test_the_run_id_is_stable_for_the_same_report() -> None:
    assert (
        parse_report(json_reporter_report()).run_id == parse_report(json_reporter_report()).run_id
    )


def test_a_different_report_gets_a_different_run_id() -> None:
    other = json_reporter_report()
    other["suites"][0]["suites"][0]["specs"][0]["title"] = "something else"
    assert parse_report(json_reporter_report()).run_id != parse_report(other).run_id


def test_the_test_key_separates_the_same_scenario_across_projects() -> None:
    report = json_reporter_report()
    report["suites"][0]["suites"][0]["specs"][0]["tests"].append(
        {"projectName": "sg-uat", "status": "expected", "results": [{"duration": 10, "errors": []}]}
    )
    keys = {item.test_key for item in parse_report(report).results}
    assert len(keys) == 3


def test_an_unrecognised_payload_is_refused() -> None:
    with pytest.raises(ReportFormatError):
        parse_report({"something": "else"})


# --- HTML report extraction -------------------------------------------------


def html_with_embedded(report: dict[str, Any], details: dict[str, dict[str, Any]]) -> str:
    """Build an index.html the way the HTML reporter does: a base64 zip at the end."""
    import base64
    import io
    import json
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("report.json", json.dumps(report))
        for name, content in details.items():
            archive.writestr(name, json.dumps(content))
    encoded = base64.b64encode(buffer.getvalue()).decode()
    return f'<!doctype html><script>window.x="data:application/zip;base64,{encoded}"</script>'


def test_errors_are_merged_from_the_per_file_json() -> None:
    """report.json has no errors; the per-file JSON does. Without the merge a
    failure would arrive with no message."""
    from qa_dashboard.ingest.playwright import extract_report_json_from_html

    summary = html_report_json()
    test = summary["files"][0]["tests"][0]
    test["outcome"] = "unexpected"
    test["results"] = [{"attachments": []}, {"attachments": []}]

    detail = {
        "fileId": "abc123",
        "tests": [
            {
                "testId": "t1",
                "results": [
                    {
                        "status": "failed",
                        "errors": [{"message": "\x1b[31mError: banner missing\x1b[39m"}],
                    },
                    {"status": "failed", "errors": [{"message": "Error: banner missing"}]},
                ],
            }
        ],
    }

    report = extract_report_json_from_html(html_with_embedded(summary, {"abc123.json": detail}))
    run = parse_report(report)
    assert run.results[0].status == "failed"
    assert run.results[0].retries == 1
    assert run.results[0].error_message == "Error: banner missing"


def test_a_missing_per_file_json_still_parses() -> None:
    from qa_dashboard.ingest.playwright import extract_report_json_from_html

    report = extract_report_json_from_html(html_with_embedded(html_report_json(), {}))
    assert parse_report(report).total == 1


def test_ansi_colour_codes_are_stripped_from_errors() -> None:
    report = json_reporter_report()
    flaky = report["suites"][0]["suites"][0]["specs"][1]["tests"][0]
    flaky["results"][0]["errors"] = [{"message": "\x1b[2mexpect(\x1b[22m\x1b[31mreceived\x1b[39m)"}]
    message = next(
        item for item in parse_report(report).results if item.status == "flaky"
    ).error_message
    assert message == "expect(received)"


def test_region_and_environment_are_read_from_a_region_env_project() -> None:
    from qa_dashboard.ingest.playwright import infer_region_environment

    assert infer_region_environment(parse_report(json_reporter_report())) == ("hk", "sit")


def test_nothing_is_inferred_from_a_non_region_env_project() -> None:
    from qa_dashboard.ingest.playwright import infer_region_environment

    report = json_reporter_report()
    for spec in report["suites"][0]["suites"][0]["specs"]:
        spec["tests"][0]["projectName"] = "chromium"
    assert infer_region_environment(parse_report(report)) is None


def test_nothing_is_inferred_when_a_run_spans_projects() -> None:
    from qa_dashboard.ingest.playwright import infer_region_environment

    report = json_reporter_report()
    report["suites"][0]["suites"][0]["specs"][1]["tests"][0]["projectName"] = "sg-uat"
    assert infer_region_environment(parse_report(report)) is None
