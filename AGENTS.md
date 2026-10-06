# AGENTS.md

Notes for an agent working in this repository.

## What this is

A QA dashboard with three sections: test execution, defects, and AI
effectiveness. Data is pushed in; the dashboard only aggregates and displays it.

## Boundaries

- `ingest/` translates external formats into internal rows and makes no business decisions
- `metrics/` only reads the database and aggregates; it does not touch HTTP
- `routes/` only translates HTTP and hands the work to `metrics`
- The frontend reaches the backend only through `apps/web/src/api/client.ts`

## Know this before changing anything

**The Playwright parser is the contract with the push.** It accepts two report
shapes: json reporter output (top-level `suites`) and the `report.json`
embedded in an HTML report (top-level `files`). Tests pin both; keep both
passing.

In json reporter output, **every suite carries a `file` field**. The file-level
suite is the one whose `title == file`, not the one that has a `file`. This has
bitten once and has a regression test.

**HTML reports need the per-file JSON merged in.** The `report.json` embedded in
`index.html` is only a summary: its per-test `results` have no status and no
errors. The full results are in the same zip as `<fileId>.json`, and
`extract_report_json_from_html` merges them back in by `testId`. Without that
step a failing test has no error message. There is a test.

**The mock JIRA and the mapping file must agree.** The customfield ids in
`apps/mock-jira/mock_jira.py` match `samples/jira/field-mapping.json`, and
`tests/test_jira_sync.py` checks it. Change one, change the other. The mock
must answer unsupported JQL with 400 and never ignore it silently.

In `mock_jira.py`, keep the `Auth` header alias at module level. With
postponed annotations FastAPI resolves it from module globals; a local alias
silently turns the header into a query parameter and every request gets 401.

**JIRA field mapping is configuration, not code.** Customfield ids differ per
instance. Change `samples/jira/field-mapping.json`; do not hard-code ids in the
parser.

**Do not change the flaky definition.** Score = (passes after a retry + flips
across runs) ÷ runs. A test that always fails must score zero: it belongs under
consistently failing, not flaky. There is a test.

**Missing is not zero.** An agent log without `items` does not count toward
adoption; without `comparison` it does not count toward accuracy. Do not treat
missing data as zero to make a chart look better.

## Sign-in and tokens

- **Ingest routes accept only the bearer token**, through `require_ingest_token`. Never let them accept the session cookie: a browser attaches cookies to cross-site requests, so a cookie-authenticated push could be triggered from another page
- **Everything a person reads needs a session**: the dashboard routes and `/reports/...`. `/health` stays open because `run-local.sh` polls it
- **Reports go through `routes/reports.py`, not a static mount**, and `storage.resolve_report_file` keeps every path inside that run's folder. The storage root also holds the generated session secret, so this check matters
- **Disabling an account or changing its password must bump `session_version`**; that is what ends existing sessions
- **Every sign-in failure gets one message**, whether the username is unknown, the password is wrong, or the account is disabled. An unknown username still runs a password check, so timing does not reveal it either
- **Never print or log a password, the ingest token, or the session secret.** The CLI reads passwords with `getpass` or `--password-stdin`, never as arguments, and the push scripts pass the token in a header file
- **Make targets take `NAME=`**, not `USER=`: the shell already sets `USER`
- Tests lower the scrypt cost through an autouse fixture in `conftest.py`. Never lower `SCRYPT_N` in the code itself

## Chart rules

Read the `dataviz` skill before changing any chart. Already decided:

- Categorical colours use only the first three slots (blue, orange, aqua), checked for colour-vision deficiency
- Status colours (passed, failed, flaky) always come with an icon and a label, never colour alone
- Ordered categories (severity, age buckets) use shades of one hue, not a rainbow
- Unordered categories (component, project) all use one colour; never colour by value
- No dual y-axes
- Every chart has a table view
- One hero number per page

## After a change

```bash
make verify              # format, lint, types, tests, frontend build
make up && make demo     # start and load demo data
make user-add NAME=you   # then sign in and click through
make push-report         # push a real report and check View report opens it
```

If you change an endpoint's shape, update `docs/ci-integration.md` as well. It
is the contract for whoever pushes data.

## Demo data

`scripts/generate_demo_data.py` produces fictional data so a fresh clone has
something to show. Do not use it as test fixtures; the tests in
`apps/api/tests/` carry their own.
