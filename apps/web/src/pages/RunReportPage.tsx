/**
 * One run's report.
 *
 * When the push included the `playwright-html` bundle we show the genuine
 * Playwright report, traces and screenshots included. When only the report data
 * was pushed we fall back to a suite tree rendered from it, which is all we have.
 */
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { RunDetail, TestStatus } from '../api/types'
import { formatPercent } from '../charts/primitives'
import { STATUS_STYLE, StatusTag } from '../components/status'

interface SuiteNode {
  name: string
  tests: {
    title: string
    project: string
    status: TestStatus
    durationMs: number
    retries: number
    error: string | null
  }[]
}

export function RunReportPage({ runId, onBack }: { runId: string; onBack: () => void }) {
  const [run, setRun] = useState<RunDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    api
      .run(runId)
      .then((value) => active && setRun(value))
      .catch((caught: Error) => active && setError(caught.message))
    return () => {
      active = false
    }
  }, [runId])

  if (error) return <p className="empty">{error}</p>
  if (!run) return <p className="empty">Loading…</p>

  const executed = run.total - run.skipped

  return (
    <>
      <button type="button" className="link-button" onClick={onBack} style={{ marginBottom: '0.75rem' }}>
        ← Back to test execution
      </button>

      <section className="card" style={{ marginBottom: '1rem' }}>
        <div className="card-head">
          <h2>
            {run.region}-{run.environment} · build {run.build_number ?? '—'}
          </h2>
          <span className="muted" style={{ fontSize: 12 }}>
            {run.started_at.replace('T', ' ').slice(0, 19)} · took {(run.duration_ms / 1000).toFixed(1)}s
          </span>
        </div>
        <p className="sub">
          {run.job_name ?? '—'}
          {run.branch ? ` · ${run.branch}` : ''}
          {run.commit_sha ? ` · ${run.commit_sha.slice(0, 8)}` : ''}
          {run.ci_url ? (
            <>
              {' · '}
              <a href={run.ci_url} target="_blank" rel="noreferrer">
                CI build
              </a>
            </>
          ) : null}
        </p>
        <div className="legend">
          <span>
            Pass rate <b>{formatPercent(executed ? (run.passed + run.flaky) / executed : null)}</b>
          </span>
          <span><i style={{ background: STATUS_STYLE.passed.color }} />✓ Passed {run.passed}</span>
          <span><i style={{ background: STATUS_STYLE.flaky.color }} />⚠ Flaky {run.flaky}</span>
          <span><i style={{ background: STATUS_STYLE.failed.color }} />✕ Failed {run.failed}</span>
          <span><i style={{ background: STATUS_STYLE.skipped.color }} />– Skipped {run.skipped}</span>
        </div>
      </section>

      {run.bundle_url ? (
        <section className="card">
          <div className="card-head">
            <h2>Playwright report</h2>
            <a href={run.bundle_url} target="_blank" rel="noreferrer" className="link-button">
              Open in a new tab
            </a>
          </div>
          <p className="sub">The original report as it was pushed, with traces, screenshots, and videos.</p>
          <iframe className="report-frame" src={run.bundle_url} title="Playwright HTML report" />
        </section>
      ) : (
        <JsonFallback run={run} />
      )}
    </>
  )
}

function JsonFallback({ run }: { run: RunDetail }) {
  const suites = flatten(run.report)
  return (
    <section className="card">
      <div className="card-head">
        <h2>Test details</h2>
      </div>
      <p className="sub">
        This run was pushed without the HTML bundle, so this view is rendered from the report
        data. For traces and screenshots, push the <span className="mono">playwright-html</span>{' '}
        folder as well, which <span className="mono">make push-report</span> does by default.
      </p>
      {suites.map((suite) => (
        <div key={suite.name} style={{ marginTop: '1rem' }}>
          <h3 style={{ fontSize: 13, margin: '0 0 0.3rem' }}>{suite.name || '(no feature)'}</h3>
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Project</th>
                  <th>Result</th>
                  <th className="num">Duration</th>
                  <th className="num">Retries</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {suite.tests.map((test) => (
                  <tr key={`${suite.name}-${test.title}-${test.project}`}>
                    <td>{test.title}</td>
                    <td className="mono">{test.project}</td>
                    <td>
                      <StatusTag status={test.status} />
                    </td>
                    <td className="num">{(test.durationMs / 1000).toFixed(1)}s</td>
                    <td className="num">{test.retries}</td>
                    <td>{test.error ? <div className="err">{test.error}</div> : <span className="muted">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  )
}

/** Playwright embeds terminal colour codes in assertion messages. */
const ANSI_ESCAPE = new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*[A-Za-z]`, 'g')

const OUTCOME: Record<string, TestStatus> = {
  expected: 'passed',
  unexpected: 'failed',
  flaky: 'flaky',
  skipped: 'skipped',
}

/** Walk either report shape into a flat suite -> tests list. */
function flatten(report: unknown): SuiteNode[] {
  const payload = report as Record<string, unknown>
  const byName = new Map<string, SuiteNode>()

  const push = (name: string, test: SuiteNode['tests'][number]) => {
    const node = byName.get(name) ?? { name, tests: [] }
    node.tests.push(test)
    byName.set(name, node)
  }

  const readResults = (results: unknown): { error: string | null; retries: number } => {
    const list = Array.isArray(results) ? (results as Record<string, unknown>[]) : []
    let error: string | null = null
    for (const item of list) {
      const errors = item.errors as { message?: string }[] | undefined
      if (errors?.length && errors[0].message) {
        error = errors[0].message.replace(ANSI_ESCAPE, '')
        break
      }
    }
    return { error, retries: Math.max(0, list.length - 1) }
  }

  if (Array.isArray(payload?.suites)) {
    const walk = (suite: Record<string, unknown>, path: string[]) => {
      const title = String(suite.title ?? '')
      const file = String(suite.file ?? '')
      const nextPath = file && title === file ? path : title ? [...path, title] : path

      for (const spec of (suite.specs as Record<string, unknown>[]) ?? []) {
        for (const test of (spec.tests as Record<string, unknown>[]) ?? []) {
          const { error, retries } = readResults(test.results)
          const durations = ((test.results as Record<string, unknown>[]) ?? []).reduce(
            (sum, item) => sum + Number(item.duration ?? 0),
            0,
          )
          push(nextPath.join(' › '), {
            title: String(spec.title ?? ''),
            project: String(test.projectName ?? ''),
            status: OUTCOME[String(test.status ?? '')] ?? 'failed',
            durationMs: durations,
            retries,
            error,
          })
        }
      }
      for (const child of (suite.suites as Record<string, unknown>[]) ?? []) walk(child, nextPath)
    }
    for (const suite of payload.suites as Record<string, unknown>[]) walk(suite, [])
  } else if (Array.isArray(payload?.files)) {
    for (const entry of payload.files as Record<string, unknown>[]) {
      for (const test of (entry.tests as Record<string, unknown>[]) ?? []) {
        const { error, retries } = readResults(test.results)
        push(((test.path as string[]) ?? []).join(' › '), {
          title: String(test.title ?? ''),
          project: String(test.projectName ?? ''),
          status: OUTCOME[String(test.outcome ?? '')] ?? 'failed',
          durationMs: Number(test.duration ?? 0),
          retries,
          error,
        })
      }
    }
  }

  return [...byName.values()]
}
