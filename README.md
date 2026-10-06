# QA Dashboard

A QA dashboard with three sections: **test execution**, **defects**, and **AI
effectiveness**.

Data is pushed in; the dashboard never pulls. For now everything runs on one
laptop: Playwright reports are pushed with a script, and JIRA is a local mock.

```
your test repo ──(make push-report)──────┐
mock JIRA :8002 ──(make sync-jira)───────┼──► API :8001 ──► SQLite ──► dashboard :5174
agent run logs ──(POST)──────────────────┘
```

## Getting started

```bash
make setup                  # install dependencies and create .env with generated secrets
make up                     # start the API :8001, the dashboard :5174, and the mock JIRA :8002
make user-add NAME=alice    # create your account; prompts for a password of 12+ characters
make demo                   # load demo data
```

Open http://127.0.0.1:5174 and sign in.

`make demo` pushes 21 days of generated Playwright reports and agent logs, then
syncs defects from the mock JIRA. The demo data is fictional; `make clean`
removes it.

## Day to day

### Push your own test report

```bash
cd ~/repository/playwright-UI-auto-v2 && npm test -- --project=hk-sit
cd ~/repository/qa-dashboard && make push-report APP=QAD
```

**No Playwright config change is needed.** `index.html` already embeds the
report data, and the dashboard reads it directly. Region and environment come
from the project name (`hk-sit` → `hk` / `sit`).

### Sync defects

```bash
make sync-jira
```

This pulls from the mock JIRA through the same path a real JIRA will use later.
To simulate a new bug or close one, see
[docs/ci-integration.md](docs/ci-integration.md).

## The three sections

### 1. Test execution

- Pass rate, passed / failed / flaky / skipped counts, and the change from the previous day
- Pass rate trend (the y-axis starts just below the lowest point; from zero, 90% and 98% would look the same)
- Pass rate by project, which here means by region and environment
- **Recent runs**: View report opens that run's Playwright report
- **Consistently failing tests**: they fail every time, so they are broken
- **Flaky test ranking**: they pass and fail on and off

#### View report

A push sends the whole `playwright-html` folder. The dashboard stores it as is,
so View report opens **your original Playwright report**, with traces,
screenshots, and videos.

A push without the bundle (`--no-bundle`) shows test details rendered from the
report data instead: grouped by feature, with result, duration, retries, and
error. There are no traces or screenshots in that view, and it does not pretend
there are.

#### Flaky is not the same as broken

```
flaky score = (passes after a retry + pass/fail flips across runs) ÷ runs
```

- **Passes after a retry**: Playwright's own `flaky` status. It needs `retries`; your config sets 1 when `CI=true`
- **Flips**: ordered by time, one run passes and the next fails, or the reverse

A test that always fails scores zero on both, so it **stays off the flaky
ranking** and shows under Consistently failing tests instead. One needs a code
fix, the other a test fix, so they are kept apart.

A test seen fewer than 3 times is not ranked. Two runs are not evidence.

Note: locally `retries` is 0, so a report pushed from a laptop has no
Playwright `flaky` status. Flakiness then shows only as flips between runs. Run
with `CI=true` to get the retry signal.

### 2. Defects

- **Defect escape rate**: defects found in production ÷ all defects
- New, resolved, and open on one chart, to see whether fixes keep up
- Breakdowns by severity, phase found, component, and root cause
- How long open defects have been open
- Mean time to resolve

A phase the dashboard cannot recognise counts as `testing` rather than being
guessed, so the escape rate can only be understated, never inflated. When the
severity field is empty, severity is derived from priority. Stories and tasks
are not counted as defects.

### 3. AI effectiveness

**Adoption** asks whether a person kept the output. It comes from the review
record:

```
adoption            = accepted items ÷ generated items
unchanged adoption  = items accepted without edits ÷ generated items
```

The gap between the two is the real cost. High adoption with low unchanged
adoption means the output was kept but had to be rewritten.

**Accuracy** asks whether the output was right, compared with reviewed Golden
tests:

```
precision = matched ÷ (matched + extra)     how much of the output was right
recall    = matched ÷ Golden total          how much of what it should find it found
F1        = the harmonic mean of the two
```

Precision and recall are shown separately. A single "accuracy" number hides
problems: an agent that produces one correct item scores 100% precision while
doing almost nothing.

The section also covers hallucination rate, cost, cost per accepted item, and
comparisons by agent, model, and prompt version.

**Without a Golden set there is no accuracy.** Accuracy compares an agent's
output with feature files a person has already reviewed.

When a log has no `items` or no `comparison`, that run is **left out** of the
affected metric instead of counting as zero.

## Commands

```bash
make setup                               # install dependencies and create .env with generated secrets
make up                                  # start the services
make down                                # stop them
make user-add NAME=alice                 # create an account (prompts for the password)
make user-list                           # list accounts
make user-reset-password NAME=alice      # set a new password; ends that account's sessions
make user-disable NAME=alice             # disable an account and end its sessions
make user-enable NAME=alice              # re-enable an account
make push-report [REPORT=dir] [APP=code] # push a Playwright report
make sync-jira                           # sync defects from the mock JIRA
make demo                                # load demo data
make test                                # backend tests
make verify                              # format, lint, types, tests, frontend build
make clean                               # remove the database (accounts included), uploaded reports, and demo data
```

Account commands take `NAME=`, not `USER=`, because the shell already sets `USER`
to your login name.

## API

| Method | Path | Needs | Purpose |
|---|---|---|---|
| `POST` | `/api/v1/session` | — | Sign in |
| `GET` | `/api/v1/session` | session | The signed-in account |
| `DELETE` | `/api/v1/session` | — | Sign out |
| `POST` | `/api/v1/ingest/playwright` | ingest token | Push a Playwright report (`index.html` or json reporter output), optionally with the bundle |
| `POST` | `/api/v1/ingest/jira` | ingest token | Import JIRA issues |
| `POST` | `/api/v1/ingest/agent-runs` | ingest token | Push agent run logs |
| `GET` | `/api/v1/filters` | session | Values for the filter row |
| `GET` | `/api/v1/execution` | session | Test execution |
| `GET` | `/api/v1/defects` | session | Defects |
| `GET` | `/api/v1/ai` | session | AI effectiveness |
| `GET` | `/api/v1/runs/{id}` | session | One run in detail |
| `GET` | `/reports/{id}/...` | session | A hosted Playwright HTML report |
| `GET` | `/health` | — | Health check |

The read endpoints share one set of filters: `days` (1–180),
`application_code`, `region`, and `environment`. Interactive API docs:
http://127.0.0.1:8001/docs .

The mock JIRA endpoints are listed in [docs/ci-integration.md](docs/ci-integration.md).

## Accounts and security

**People sign in with a local account.** Create accounts with `make user-add`;
there is no sign-up page. There is one role: everyone who signs in sees
everything.

**Scripts push with a token, not a sign-in.** `make setup` puts a random
`QA_INGEST_TOKEN` in `.env`, and `make push-report`, `make sync-jira`, and
`make demo` send it for you. For CI, see
[docs/ci-integration.md](docs/ci-integration.md).

How it is protected:

- **Passwords** are hashed with scrypt and a random salt per password. The password itself is never stored, logged, or taken as a command-line argument
- **Sessions** are signed `HttpOnly`, `SameSite=Lax` cookies that last 12 hours (`QA_SESSION_MAX_AGE_HOURS`). Resetting a password or disabling an account ends that account's sessions at once
- **Failed sign-ins** lock the username for 15 minutes after 5 attempts
- **Reports are private.** A report holds screenshots and traces of the application under test, so `/reports/...` needs a session like the rest of the dashboard
- **Pushes accept only the token, never the session cookie.** A browser attaches cookies to requests from any site, but never a bearer token, so another page cannot push data through a signed-in browser
- **Replies don't reveal accounts.** A wrong password, an unknown username, and a disabled account all get the same message
- **Secrets stay out of git.** `.env` is ignored, and nothing prints the token or the session secret

When the dashboard is served over HTTPS, set `QA_SESSION_COOKIE_SECURE=true`.

## Moving to real systems later

- **Jenkins**: add one curl step to the Jenkinsfile that pushes `index.html` and the bundle. Still no Playwright config change
- **Real JIRA**: set `QA_JIRA_BASE_URL` and a token, update the field mapping file, and run `sync_jira.py` without `--mock`

The steps are in the last section of [docs/ci-integration.md](docs/ci-integration.md).

## Design choices

- **One filter row above every chart.** All charts share the same slice, so they can be read against each other
- **Every chart can switch to a table** with Show table. No number depends on colour alone
- **Status colours always come with an icon and a label**: ✓ Passed / ⚠ Flaky / ✕ Failed / – Skipped
- **The palette is checked for colour-vision deficiency.** The categorical colours are three validated slots that pass in both light and dark mode
- **Ordered categories use shades of one hue**, such as severity. No rainbow scales
- **No dual y-axes.** Two measures on different scales get two charts

## Known limitations

- Storage is SQLite in a single process
- Sign-in lockout lives in memory: a restart clears it, and anyone who knows a username can lock that account for 15 minutes
- There is no self-service password reset; someone with repository access runs `make user-reset-password`
- One shared ingest token: rotating it means updating `.env` and every place that pushes
- The session cookie is not marked `Secure` by default, because the local setup runs over plain HTTP
- Uploaded reports are never cleaned up, so `storage/` keeps growing
- The mock JIRA keeps its data in memory and resets on restart
- The mock JIRA supports only a small subset of JQL
- "Open" in the defect trend is computed per day on request, which slows down with a lot of data
- The frontend has no routing, so a refresh returns to the first tab
