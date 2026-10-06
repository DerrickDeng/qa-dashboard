# Getting data in

The dashboard never pulls data; everything is pushed. There are three sources.
This page first covers **how to use them on your own laptop today**, then what
changes when you move to a real Jenkins and a real JIRA.

## Authentication

Every push must send the ingest token:

```
Authorization: Bearer <QA_INGEST_TOKEN>
```

`make setup` generates the token into `.env`. `make push-report`,
`make sync-jira`, and `make demo` read it from there, so on your laptop there is
nothing to add. A push without it gets `401`. If the dashboard has no token
configured at all, pushes get `503`.

Pushes accept only this token, never a browser session, so a signed-in browser
cannot be used to push data from another site.

To use the token in a manual `curl`:

```bash
export QA_INGEST_TOKEN="$(grep '^QA_INGEST_TOKEN=' .env | cut -d= -f2-)"
```

## 1. Playwright reports: push from your laptop

### No config change

Your `playwright.config.ts` already writes an HTML report. The end of
`index.html` embeds the full report data, and the dashboard parses it from
there. **You do not need to add the json reporter.**

This was checked on one run exported both ways, as json reporter output and as
an HTML report. Both parse to identical rows: results, retry counts, and error
messages.

### Run the tests, then push

```bash
# Run the tests as usual in your test repo
cd ~/repository/playwright-UI-auto-v2
npm test -- --project=hk-sit

# Push from the dashboard repo
cd ~/repository/qa-dashboard
make push-report APP=QAD
```

`make push-report` reads `../playwright-UI-auto-v2/reports/playwright-html` by
default. If your report is somewhere else:

```bash
make push-report REPORT=/path/to/playwright-html APP=QAD
```

The push script:

- zips the whole `playwright-html` folder and sends it, so View report opens the original report with traces, screenshots, and videos
- **reads region and environment from the project name**: `hk-sit` becomes region `hk`, environment `sit`
- records the test repo's current commit and branch
- labels the build `local-<timestamp>`
- sends the ingest token from `.env`

Call the script directly for more options:

```bash
scripts/push_playwright_report.sh [report-dir] \
  --app QAD --product WEB \
  --region hk --env sit \      # only when the project name is not region-env
  --build 20260913-a \
  --no-bundle                  # send index.html only, without the zip
```

### Behaviour to know about

- **Pushing the same report twice does not double-count.** The run id is derived from the report content, so the second push replaces the first, bundle included
- **Region is not guessed for a run that spans several projects.** It is inferred only when the whole report has exactly one project in `xx-yyy` form; otherwise pass `--region` and `--env`
- **Every `npm test` overwrites the previous report folder.** To keep a run, push it before running the tests again

## 2. JIRA: a local mock

### What the mock is

`make up` also starts a mock JIRA at `http://127.0.0.1:8002`. It implements the
parts of the real JIRA REST API the sync uses, and returns the same data shapes:

| Endpoint | Purpose |
|---|---|
| `GET /rest/api/2/search` | JQL search, paged with `startAt` / `maxResults` |
| `GET /rest/api/2/field` | Field list, for looking up customfield ids |
| `POST /rest/api/2/issue` | Create an issue, to simulate a newly reported bug |
| `POST /rest/api/2/issue/{key}/transitions` | Close an issue |
| `GET /browse/{key}` | A simple detail page, so defect keys in the dashboard are clickable |

`/rest/api/3/...` works too and behaves the same.

It holds two projects (QAD and SHOP) and the last 60 days of issues. Besides
bugs there are stories and tasks, and about one bug in ten has no severity or
other custom fields filled in. That is deliberate: real JIRA looks like this,
and the dashboard has to handle it.

Authentication works like real JIRA as well: a request without a token gets
401. The token is `mock-token`, sent as either Bearer or Basic.

### Sync into the dashboard

```bash
make sync-jira
```

This runs **the same flow a real JIRA will use**: page through the search, parse
with the field mapping, and push to the dashboard. Switching to real JIRA later
changes only the address and the token.

### Simulate a newly reported bug

```bash
curl -X POST http://127.0.0.1:8002/rest/api/2/issue \
  -H "Authorization: Bearer mock-token" -H "Content-Type: application/json" \
  -d '{
    "fields": {
      "project": {"key": "QAD"},
      "issuetype": {"name": "Bug"},
      "summary": "Login captcha sometimes fails to load",
      "components": [{"name": "Login"}],
      "customfield_10050": {"value": "Critical"},
      "customfield_10051": {"value": "production"},
      "customfield_10052": {"value": "Code defect"}
    }
  }'

make sync-jira    # the new bug now shows in the dashboard
```

Close it, using the key the create call returned:

```bash
curl -X POST http://127.0.0.1:8002/rest/api/2/issue/QAD-4200/transitions \
  -H "Authorization: Bearer mock-token" -H "Content-Type: application/json" \
  -d '{"transition": {"id": "31"}}'
```

The mock keeps its data in memory, so a restart returns it to the starting state.

### Field mapping

`samples/jira/field-mapping.json` currently holds the mock JIRA's field ids:

| Dashboard concept | Field id | JIRA field name |
|---|---|---|
| Severity | `customfield_10050` | Severity |
| Phase found | `customfield_10051` | Found In Phase |
| Root cause | `customfield_10052` | Root Cause |

Looking up field ids works the same way as on real JIRA, so you can practise on
the mock:

```bash
curl -s -H "Authorization: Bearer mock-token" http://127.0.0.1:8002/rest/api/2/field
```

A test checks that this mapping file matches the mock. Change one without the
other and the test fails.

### Supported JQL

The mock implements a small subset of JQL:

```
project = QAD                    project in (QAD, SHOP)
issuetype = Bug                   issuetype in (Bug, Defect)
status = "In Progress"            statusCategory = Done
created >= -30d                   created >= "2026-09-01"     (also updated, and <= > <)
Join conditions with AND; end with ORDER BY created|updated ASC|DESC if needed
```

**Anything unsupported returns 400; it is never silently ignored.** For
example `sprint in openSprints()`. Real JIRA reacts to bad JQL the same way.

```bash
cd apps/api && uv run python ../../scripts/sync_jira.py --mock \
  --jql 'project = QAD AND created >= -14d ORDER BY created DESC'
```

## 3. Agent run logs

After an agent runs and a person reviews the output, push this JSON (one object
or an array):

```json
{
  "run_id": "tc-2026-09-11-001",
  "agent": "testcase-agent",
  "model": "claude-opus-5",
  "prompt_version": "v4",
  "started_at": "2026-09-11T02:14:00Z",
  "duration_ms": 18400,
  "input_ref": "LAB-101",
  "tokens": { "input": 7400, "output": 2100 },
  "cost_usd": 0.042,

  "items": [
    { "item_id": "s1", "accepted": true,  "edited": false, "edit_distance": 0 },
    { "item_id": "s2", "accepted": true,  "edited": true,  "edit_distance": 34 },
    { "item_id": "s3", "accepted": false, "edited": false, "edit_distance": 0 }
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

```bash
curl -X POST http://127.0.0.1:8001/api/v1/ingest/agent-runs \
  -H "Authorization: Bearer $QA_INGEST_TOKEN" \
  -F "logs=@agent-runs.json;type=application/json"
```

- No `items` → the run is left out of adoption
- No `comparison` → the run is left out of accuracy

**Missing means "no data", not zero.** Counting unreviewed runs as zero would
only produce a false number.

`comparison` is meaningful only against a reviewed Golden set: feature files a
person has already reviewed for the same requirement.

## Moving to real systems later

### Jenkins

Store the ingest token as a Jenkins **Secret text** credential, for example
`qa-dashboard-ingest-token`. Then add a step to the `Report Uploading` stage.
**Still no Playwright config change**; push `index.html` directly:

```groovy
withCredentials([string(credentialsId: 'qa-dashboard-ingest-token', variable: 'QA_INGEST_TOKEN')]) {
    try {
        sh """
          cd reports && zip -qr playwright-html.zip playwright-html && cd ..
          curl -fsS -X POST "${QA_DASHBOARD_URL}/api/v1/ingest/playwright" \\
            -H "Authorization: Bearer \$QA_INGEST_TOKEN" \\
            -F "report=@reports/playwright-html/index.html;type=text/html" \\
            -F "bundle=@reports/playwright-html.zip;type=application/zip" \\
            -F "application_code=QAD" \\
            -F "job_name=${JOB_NAME}" \\
            -F "build_number=${BUILD_NUMBER}" \\
            -F "commit_sha=${env.GIT_COMMIT ?: ''}" \\
            -F "ci_url=${BUILD_URL}"
        """
    } catch (e) {
        // A failed push should not fail the build
        echo "Push to QA dashboard failed: ${e}"
    }
}
```

`\$QA_INGEST_TOKEN` is escaped on purpose. The shell expands it, not Groovy, so
Jenkins can mask the secret and it never lands in the generated script.

Region and environment are read from `--project=${region}-${exec_env}`, so they
do not need to be sent.

### Real JIRA

```bash
export QA_JIRA_BASE_URL=https://jira.your-company.com
export QA_JIRA_API_TOKEN=...          # a personal access token on Data Center
# export QA_JIRA_EMAIL=...            # Jira Cloud only: email plus API token
export QA_JIRA_API_VERSION=2
export QA_JIRA_JQL='project = QAD AND issuetype = Bug AND created >= -90d ORDER BY created DESC'

cd apps/api && uv run python ../../scripts/sync_jira.py     # without --mock
```

The sync sends the dashboard's ingest token from `QA_INGEST_TOKEN`, or from
`.env`, the same as on your laptop.

Two more steps:

1. **Update the field mapping.** Look up the real ids for severity, phase found, and root cause at `<your JIRA>/rest/api/2/field` and put them in `samples/jira/field-mapping.json`. If they are wrong, the sync warns that no defect has a recognised severity
2. **Confirm the search endpoint.** Data Center uses `/rest/api/2/search`, the same as the mock. Newer Jira Cloud sites moved search to `/rest/api/3/search/jql`, which pages differently, so check this before connecting to Cloud

The token is used only for the JIRA request. It is not stored in the database,
not sent to the dashboard, and not printed.
