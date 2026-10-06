import { BarChart } from '../charts/BarChart'
import { LineChart } from '../charts/LineChart'
import { StackedBar } from '../charts/StackedBar'
import { ChartCard, formatNumber, formatPercent, shortDate } from '../charts/primitives'
import { Hero, StatTile } from '../components/Tiles'
import { STATUS_STYLE, StatusSparkline } from '../components/status'
import type { ExecutionSection } from '../api/types'

interface Props {
  data: ExecutionSection
  onOpenRun: (runId: string) => void
}

export function ExecutionPage({ data, onOpenRun }: Props) {
  const { summary, trend, by_project: byProject, runs, flaky_ranking: flaky } = data

  const delta =
    summary.pass_rate !== null && summary.previous_pass_rate !== null
      ? summary.pass_rate - summary.previous_pass_rate
      : null

  return (
    <>
      <div className="grid grid-kpi" style={{ marginBottom: '1rem' }}>
        <Hero
          label={summary.day ? `Pass rate on ${summary.day}` : 'Pass rate'}
          value={formatPercent(summary.pass_rate)}
          note={
            delta === null
              ? `${summary.runs} runs`
              : `${delta >= 0 ? '↑' : '↓'} ${Math.abs(delta * 100).toFixed(1)} pts vs the previous day · ${summary.runs} runs`
          }
        />
        <StatTile
          label="Passed"
          value={formatNumber(summary.passed)}
          note="Plus flaky tests that passed on retry"
          color={STATUS_STYLE.passed.color}
        />
        <StatTile
          label="Failed"
          value={formatNumber(summary.failed)}
          note="Still failing after retries"
          color={STATUS_STYLE.failed.color}
        />
        <StatTile
          label="Flaky"
          value={formatNumber(summary.flaky)}
          note="Failed first, passed on retry"
          color={STATUS_STYLE.flaky.color}
        />
        <StatTile
          label="Total tests"
          value={formatNumber(summary.total)}
          note={`${summary.skipped} skipped`}
        />
      </div>

      <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
        <ChartCard
          title="Pass rate trend"
          subtitle="Daily totals across every run in the current filter"
          table={
            <table>
              <caption>Pass rate trend</caption>
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num">Total</th>
                  <th className="num">Passed</th>
                  <th className="num">Failed</th>
                  <th className="num">Flaky</th>
                  <th className="num">Pass rate</th>
                </tr>
              </thead>
              <tbody>
                {trend.map((point) => (
                  <tr key={point.date}>
                    <td>{point.date}</td>
                    <td className="num">{point.total}</td>
                    <td className="num">{point.passed}</td>
                    <td className="num">{point.failed}</td>
                    <td className="num">{point.flaky}</td>
                    <td className="num">{formatPercent(point.pass_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          <LineChart
            labels={trend.map((point) => shortDate(point.date))}
            series={[
              {
                key: 'pass_rate',
                label: 'Pass rate',
                color: 'var(--series-1)',
                values: trend.map((point) => point.pass_rate),
              },
            ]}
            yMax={1}
            yMin={Math.min(0.8, Math.max(0, Math.min(...trend.map((p) => p.pass_rate ?? 1)) - 0.05))}
            formatValue={(value) => formatPercent(value)}
            formatTick={(value) => `${(value * 100).toFixed(0)}%`}
          />
          <p className="sub" style={{ marginTop: '0.6rem', marginBottom: 0 }}>
            The y-axis starts just below the lowest point, not at zero. From zero, the gap
            between 90% and 98% would flatten out.
          </p>
        </ChartCard>

        <ChartCard
          title="Results on the latest day"
          subtitle={summary.day ? `${summary.total} tests on ${summary.day}` : 'No data yet'}
          table={
            <table>
              <caption>Results on the latest day</caption>
              <thead>
                <tr>
                  <th>Result</th>
                  <th className="num">Tests</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>✓ Passed</td><td className="num">{summary.passed}</td></tr>
                <tr><td>⚠ Flaky</td><td className="num">{summary.flaky}</td></tr>
                <tr><td>✕ Failed</td><td className="num">{summary.failed}</td></tr>
                <tr><td>– Skipped</td><td className="num">{summary.skipped}</td></tr>
              </tbody>
            </table>
          }
        >
          <StackedBar
            segments={[
              { key: 'passed', label: 'Passed', value: summary.passed, color: STATUS_STYLE.passed.color, icon: '✓' },
              { key: 'flaky', label: 'Flaky', value: summary.flaky, color: STATUS_STYLE.flaky.color, icon: '⚠' },
              { key: 'failed', label: 'Failed', value: summary.failed, color: STATUS_STYLE.failed.color, icon: '✕' },
              { key: 'skipped', label: 'Skipped', value: summary.skipped, color: STATUS_STYLE.skipped.color, icon: '–' },
            ]}
          />
          <p className="sub" style={{ marginTop: '0.9rem', marginBottom: 0 }}>
            Pass rate counts executed tests only; skipped tests are left out.
          </p>
        </ChartCard>
      </div>

      <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
        <ChartCard
          title="Pass rate by project"
          subtitle="Each project is a region-environment pair"
          table={
            <table>
              <caption>Pass rate by project</caption>
              <thead>
                <tr>
                  <th>Project</th>
                  <th className="num">Total</th>
                  <th className="num">Failed</th>
                  <th className="num">Flaky</th>
                  <th className="num">Pass rate</th>
                </tr>
              </thead>
              <tbody>
                {byProject.map((row) => (
                  <tr key={row.project}>
                    <td>{row.project}</td>
                    <td className="num">{row.total}</td>
                    <td className="num">{row.failed}</td>
                    <td className="num">{row.flaky}</td>
                    <td className="num">{formatPercent(row.pass_rate)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          <BarChart
            data={byProject.map((row) => ({
              name: row.project,
              value: Math.round((row.pass_rate ?? 0) * 1000) / 10,
              note: `${row.total} tests`,
            }))}
            formatValue={(value) => `${value.toFixed(1)}%`}
            labelWidth={90}
            max={100}
          />
        </ChartCard>

        <RunsCard runs={runs} onOpenRun={onOpenRun} />
      </div>

      <FlakyCard data={data} flaky={flaky} />

      {data.top_failures.length > 0 && (
        <section className="card" style={{ marginTop: '1rem' }}>
          <div className="card-head">
            <h2>Consistently failing tests</h2>
          </div>
          <p className="sub">
            These fail every time. They are broken, not flaky. Fix them first, then work
            through the flaky ranking above.
          </p>
          <div className="scroll-x">
            <table>
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Feature</th>
                  <th>Project</th>
                  <th className="num">Failed / runs</th>
                  <th>Latest error</th>
                </tr>
              </thead>
              <tbody>
                {data.top_failures.map((row) => (
                  <tr key={row.test_key}>
                    <td>{row.title}</td>
                    <td className="muted">{row.feature || '—'}</td>
                    <td className="mono">{row.project}</td>
                    <td className="num">
                      {row.failures}/{row.runs}
                    </td>
                    <td>
                      <div className="err">{(row.error_message ?? '—').split('\n')[0]}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}

function RunsCard({ runs, onOpenRun }: { runs: ExecutionSection['runs']; onOpenRun: (id: string) => void }) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>Recent runs</h2>
      </div>
      <p className="sub">Open a run&apos;s Playwright report with View report.</p>
      <div className="scroll-x scroll-y">
        <table>
          <thead>
            <tr>
              <th>Started</th>
              <th>Project</th>
              <th>Build</th>
              <th className="num">Pass rate</th>
              <th className="num">Failed</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td className="mono">{run.started_at.replace('T', ' ').slice(0, 16)}</td>
                <td className="mono">
                  {run.region}-{run.environment}
                </td>
                <td className="mono muted">{run.build_number ?? '—'}</td>
                <td className="num">{formatPercent(run.pass_rate)}</td>
                <td className="num">{run.failed}</td>
                <td>
                  <button type="button" className="link-button" onClick={() => onOpenRun(run.id)}>
                    View report
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function FlakyCard({ data, flaky }: { data: ExecutionSection; flaky: ExecutionSection['flaky_ranking'] }) {
  return (
    <div className="grid grid-2">
      <ChartCard
        title="Flaky rate trend"
        subtitle="Share of executed tests that Playwright marked flaky each day"
        table={
          <table>
            <caption>Flaky rate trend</caption>
            <thead>
              <tr>
                <th>Date</th>
                <th className="num">Flaky</th>
                <th className="num">Executed</th>
                <th className="num">Flaky rate</th>
              </tr>
            </thead>
            <tbody>
              {data.flaky_trend.map((point) => (
                <tr key={point.date}>
                  <td>{point.date}</td>
                  <td className="num">{point.flaky}</td>
                  <td className="num">{point.executed}</td>
                  <td className="num">{formatPercent(point.flaky_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        }
      >
        <LineChart
          labels={data.flaky_trend.map((point) => shortDate(point.date))}
          series={[
            {
              key: 'flaky_rate',
              label: 'Flaky rate',
              color: 'var(--series-2)',
              values: data.flaky_trend.map((point) => point.flaky_rate),
            },
          ]}
          formatValue={(value) => formatPercent(value)}
          formatTick={(value) => `${(value * 100).toFixed(1)}%`}
        />
      </ChartCard>

      <section className="card">
        <div className="card-head">
          <h2>Flaky test ranking</h2>
        </div>
        <p className="sub">
          Score = (passes after a retry + pass/fail flips across runs) ÷ runs. A test that always
          fails scores zero and appears under Consistently failing tests below.
        </p>
        <div className="scroll-x scroll-y">
          <table>
            <thead>
              <tr>
                <th className="num">Score</th>
                <th>Test</th>
                <th>Project</th>
                <th className="num">Flaky</th>
                <th className="num">Flips</th>
                <th>Recent results</th>
              </tr>
            </thead>
            <tbody>
              {flaky.length === 0 && (
                <tr>
                  <td colSpan={6} className="muted">
                    No unstable tests in this range.
                  </td>
                </tr>
              )}
              {flaky.map((row) => (
                <tr key={row.test_key}>
                  <td className="num">
                    <b>{(row.flaky_score * 100).toFixed(0)}</b>
                  </td>
                  <td>
                    {row.title}
                    <div className="muted" style={{ fontSize: 12 }}>
                      {row.feature}
                    </div>
                  </td>
                  <td className="mono">{row.project}</td>
                  <td className="num">
                    {row.flaky_runs}/{row.runs}
                  </td>
                  <td className="num">{row.flips}</td>
                  <td>
                    <StatusSparkline statuses={row.recent} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
