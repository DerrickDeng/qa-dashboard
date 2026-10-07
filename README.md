# QA Dashboard

A QA dashboard with three sections: **test execution**, **defects**, and **AI
effectiveness**. It is also the application under test for the
[Agentic QA Workflow](https://github.com/DerrickDeng): the
[test design](https://github.com/DerrickDeng/ai-native-test-design) stories and
the [UI automation](https://github.com/DerrickDeng/ai-native-ui-automation)
evaluations use it.

Data comes in by push. The dashboard never pulls. At this time, all parts run
on one laptop: a script pushes the Playwright reports, and JIRA is a local mock.

```
your test repo ──(make push-report)──────┐
mock JIRA :8002 ──(make sync-jira)───────┼──► API :8001 ──► SQLite ──► dashboard :5174
agent run logs ──(POST)──────────────────┘
```

## Getting started

```bash
make setup                  # install dependencies and create .env with generated secrets
make up                     # start the API :8001, the dashboard :5174, and the mock JIRA :8002
make user-add NAME=alice    # create your account; asks for a password of 12 or more characters
make demo                   # load demo data
```

Open http://127.0.0.1:5174 and sign in.

`make demo` pushes 21 days of generated Playwright reports and agent logs. Then
it syncs defects from the mock JIRA. The demo data is not real. `make clean`
removes it.

## Daily use

### Push your test report

```bash
cd ~/repository/ai-native-ui-automation && npm test -- --project=hk-sit
cd ~/repository/qa-dashboard && make push-report APP=QAD
```

**You do not need to change the Playwright configuration.** `index.html`
already contains the report data, and the dashboard reads it directly. The
region and the environment come from the project name (`hk-sit` → `hk` /
`sit`).

### Sync defects

```bash
make sync-jira
```

This command pulls from the mock JIRA. A real JIRA will use the same path
later. To make a new bug or to close a bug in the mock, see
[docs/ci-integration.md](docs/ci-integration.md).

## The three sections

### 1. Test execution

- The pass rate, the passed, failed, flaky, and skipped counts, and the change
  from the previous day with data
- The pass-rate trend. The y-axis starts just below the lowest point. If it
  started at zero, 90% and 98% would look the same.
- The pass rate for each project. Here, a project is a region and an
  environment.
- **Recent runs**: View report opens the Playwright report of that run.
- **Consistently failing tests**: the tests with the most failures in the
  range. Each test in the list failed at least once. A test that fails only
  some of the time can also show here.
- **Flaky test ranking**: tests that pass and fail at different times

#### View report

A push sends the full `playwright-html` folder. The dashboard keeps it as it
is. So View report opens **your original Playwright report**, with traces,
screenshots, and videos.

A push without the bundle (`--no-bundle`) shows test details from the report
data. The details are grouped by feature, with the result, duration, retries,
and error. This view has no traces or screenshots, and it does not show links
to them.

#### Flaky is not the same as broken

```
flaky score = (passes after a retry + pass/fail flips across runs) ÷ runs that are not skipped
```

- **Passes after a retry**: the `flaky` status of Playwright. It needs
  `retries`. Your configuration sets 1 retry when `CI=true`.
- **Flips**: the runs are in time order. One run passes and the next run
  fails, or the opposite.

A test that always fails has zero for both. So it **does not go into the flaky
ranking**. It shows in Consistently failing tests. One needs a code fix, and
the other needs a test fix, so the dashboard keeps them apart.

The ranking does not include a test with fewer than 3 runs. Skipped runs count
for this limit. Two runs are not evidence.

Note: `retries` is 0 for local runs. So a report from a laptop has no
Playwright `flaky` status, and only flips between runs show flakiness. Run with
`CI=true` to get the retry signal.

### 2. Defects

- **Defect escape rate**: defects found in production ÷ all defects
- New, resolved, and open defects on one chart. It shows if fixes keep up.
- Breakdowns by severity, phase found, component, and root cause
- The age of open defects
- Mean time to resolve

If the dashboard does not recognize a phase, it counts the defect as
`testing`. It does not guess. So the escape rate can be too low, but never too
high. When the severity field is empty, the dashboard uses the priority to set
the severity. Stories and tasks are not defects.

### 3. AI effectiveness

**Adoption** tells if a person kept the output. It comes from the review
record:

```
adoption            = accepted items ÷ generated items
unchanged adoption  = items accepted without edits ÷ generated items
```

The difference between the two is the real cost. High adoption with low
unchanged adoption means that a person kept the output but had to rewrite it.

**Accuracy** tells if the output was correct. It compares the output with
reviewed Golden tests:

```
precision = matched ÷ (matched + extra)     how much of the output was correct
recall    = matched ÷ Golden total          how much of the expected output it found
F1        = the harmonic mean of the two
```

The dashboard shows precision and recall separately. One "accuracy" number
hides problems. For example, an agent that makes only one correct item gets
100% precision but does almost no work.

This section also shows the hallucination rate, the cost, the cost for each
accepted item, and comparisons by agent, model, and prompt version.

**Without a Golden set, there is no accuracy.** Accuracy compares the output of
an agent with feature files that a person has already reviewed.

When a log has no `items` or no `comparison`, the dashboard **does not use**
that run for the related metric. It does not count the run as zero.

## Commands

```bash
make setup                               # install dependencies and create .env with generated secrets
make up                                  # start the services
make down                                # stop the services
make user-add NAME=alice                 # create an account (asks for the password)
make user-list                           # list the accounts
make user-reset-password NAME=alice      # set a new password; ends the sessions of that account
make user-disable NAME=alice             # disable an account and end its sessions
make user-enable NAME=alice              # enable an account again
make push-report [REPORT=dir] [APP=code] # push a Playwright report
make sync-jira                           # sync defects from the mock JIRA
make demo                                # load demo data
make test                                # run the backend tests
make verify                              # format, lint, types, tests, and frontend build
make clean                               # remove the database (with accounts), uploaded reports, and demo data
```

The account commands use `NAME=`, not `USER=`. The shell already sets `USER` to
your login name.

## API

| Method | Path | Needs | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/session` | — | Sign in |
| `GET` | `/api/v1/session` | session | The signed-in account |
| `DELETE` | `/api/v1/session` | — | Sign out |
| `POST` | `/api/v1/ingest/playwright` | ingest token | Push a Playwright report (`index.html` or JSON reporter output), with the bundle if you want |
| `POST` | `/api/v1/ingest/jira` | ingest token | Import JIRA issues |
| `POST` | `/api/v1/ingest/agent-runs` | ingest token | Push agent run logs |
| `GET` | `/api/v1/filters` | session | Values for the filter row |
| `GET` | `/api/v1/execution` | session | Test execution |
| `GET` | `/api/v1/defects` | session | Defects |
| `GET` | `/api/v1/ai` | session | AI effectiveness |
| `GET` | `/api/v1/runs/{id}` | session | The details of one run |
| `GET` | `/reports/{id}/...` | session | A stored Playwright HTML report |
| `GET` | `/health` | — | Health check |

The read endpoints use the same filters: `days` (1–180), `application_code`,
`region`, and `environment`. The interactive API documentation is at
http://127.0.0.1:8001/docs .

[docs/ci-integration.md](docs/ci-integration.md) lists the mock JIRA endpoints.

## Accounts and security

**People sign in with a local account.** Create accounts with `make user-add`.
There is no sign-up page. There is one role: all signed-in people see all data.

**Scripts push with a token, not with a sign-in.** `make setup` puts a random
`QA_INGEST_TOKEN` in `.env`. `make push-report`, `make sync-jira`, and
`make demo` send it for you. For CI, see
[docs/ci-integration.md](docs/ci-integration.md).

How the dashboard is protected:

- **Passwords** are hashed with scrypt and a random salt for each password. The
  dashboard never stores or logs the password, and it never takes the password
  as a command-line argument.
- **Sessions** are signed `HttpOnly`, `SameSite=Lax` cookies. They last 12
  hours (`QA_SESSION_MAX_AGE_HOURS`). A password reset or an account disable
  ends the sessions of that account immediately.
- **Failed sign-ins** lock the username for 15 minutes after 5 attempts.
- **Reports are private.** A report contains screenshots and traces of the
  application under test. So `/reports/...` needs a session, like the rest of
  the dashboard.
- **Pushes accept only the token, never the session cookie.** A browser adds
  cookies to requests from all sites, but it never adds a bearer token. So
  another page cannot push data through a signed-in browser.
- **Replies do not show which accounts exist.** A wrong password, an unknown
  username, and a disabled account all get the same message.
- **Secrets stay out of Git.** Git ignores `.env`, and no command prints the
  token or the session secret.

When the dashboard runs over HTTPS, set `QA_SESSION_COOKIE_SECURE=true`.

## Move to real systems later

- **Jenkins**: add one curl step to the Jenkinsfile. The step pushes
  `index.html` and the bundle. You still do not change the Playwright
  configuration.
- **Real JIRA**: set `QA_JIRA_BASE_URL` and a token, update the field mapping
  file, and run `sync_jira.py` without `--mock`.

The last section of [docs/ci-integration.md](docs/ci-integration.md) has the
steps.

## Design choices

- **One filter row above all charts.** All charts use the same data slice, so
  you can compare them.
- **Each chart can change to a table** with Show table. No number depends on
  color only.
- **Status colors always have an icon and a label**: ✓ Passed / ⚠ Flaky /
  ✕ Failed / – Skipped.
- **The palette is checked for color-vision deficiency.** The categorical
  colors are three validated slots. They pass in light mode and in dark mode.
- **Ordered categories, such as severity, use shades of one color.** There are
  no rainbow scales.
- **No dual y-axes.** Two measures with different scales get two charts.

## Known limitations

- The storage is SQLite in one process.
- The sign-in lockout is in memory. A restart clears it. A person who knows a
  username can lock that account for 15 minutes.
- There is no self-service password reset. A person with repository access runs
  `make user-reset-password`.
- There is one shared ingest token. To change it, update `.env` and all places
  that push.
- The session cookie does not have the `Secure` flag by default, because the
  local setup uses plain HTTP.
- The dashboard does not clean up uploaded reports, so `storage/` continues to
  grow.
- The mock JIRA keeps its data in memory and resets when it restarts.
- The mock JIRA supports only a small part of JQL.
- The dashboard calculates "Open" in the defect trend for each day on each
  request. This becomes slow with a lot of data.
- The frontend has no routing, so a refresh goes back to the first tab.
