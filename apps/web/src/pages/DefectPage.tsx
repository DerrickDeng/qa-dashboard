import { BarChart } from '../charts/BarChart'
import { LineChart } from '../charts/LineChart'
import { ChartCard, formatNumber, formatPercent, shortDate } from '../charts/primitives'
import { Hero, StatTile } from '../components/Tiles'
import { SEVERITY_COLORS } from '../components/status'
import type { DefectSection, NamedCount } from '../api/types'

const PHASE_LABELS: Record<string, string> = {
  requirement: 'Requirements',
  development: 'Development',
  testing: 'Testing',
  staging: 'Staging',
  production: 'Production',
}

const STATUS_LABELS: Record<string, string> = {
  todo: 'To do',
  in_progress: 'In progress',
  done: 'Done',
}

export function DefectPage({ data }: { data: DefectSection }) {
  const { summary, trend } = data

  return (
    <>
      <div className="grid grid-kpi" style={{ marginBottom: '1rem' }}>
        <Hero
          label="Defect escape rate"
          value={formatPercent(summary.escape_rate)}
          note={`${summary.escaped} of ${summary.total} defects were found in production`}
        />
        <StatTile label="New" value={formatNumber(summary.created)} note="In the selected range" />
        <StatTile label="Resolved" value={formatNumber(summary.resolved)} note="In the selected range" />
        <StatTile
          label="Open"
          value={formatNumber(summary.open)}
          note={`${summary.open_critical} of them Blocker or Critical`}
        />
        <StatTile
          label="Mean time to resolve"
          value={summary.mttr_days === null ? '—' : `${summary.mttr_days} days`}
          note="From created to resolved"
        />
      </div>

      <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
        <ChartCard
          title="New, resolved, and open"
          subtitle="Read the three together: if open is not coming down, fixes are not keeping up"
          table={
            <table>
              <caption>Defect trend</caption>
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num">New</th>
                  <th className="num">Resolved</th>
                  <th className="num">Open</th>
                </tr>
              </thead>
              <tbody>
                {trend.map((point) => (
                  <tr key={point.date}>
                    <td>{point.date}</td>
                    <td className="num">{point.created}</td>
                    <td className="num">{point.resolved}</td>
                    <td className="num">{point.open}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          <LineChart
            labels={trend.map((point) => shortDate(point.date))}
            series={[
              { key: 'open', label: 'Open', color: 'var(--series-1)', values: trend.map((p) => p.open) },
              { key: 'created', label: 'New', color: 'var(--series-2)', values: trend.map((p) => p.created) },
              { key: 'resolved', label: 'Resolved', color: 'var(--series-3)', values: trend.map((p) => p.resolved) },
            ]}
            formatValue={(value) => formatNumber(Math.round(value))}
            formatTick={(value) => String(Math.round(value))}
          />
        </ChartCard>

        <ChartCard
          title="By severity"
          subtitle="An ordered scale in one hue; the strongest shade is the most severe"
          table={<CountTable caption="By severity" rows={data.by_severity} />}
        >
          <BarChart
            data={toBars(data.by_severity)}
            colors={SEVERITY_COLORS}
            formatValue={formatNumber}
            labelWidth={90}
          />
        </ChartCard>
      </div>

      <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
        <ChartCard
          title="By phase found"
          subtitle="Earlier is better. The production bar is the escape rate's numerator"
          table={<CountTable caption="By phase found" rows={data.by_found_phase} labels={PHASE_LABELS} />}
        >
          <BarChart
            data={toBars(data.by_found_phase, PHASE_LABELS)}
            formatValue={formatNumber}
            labelWidth={100}
          />
        </ChartCard>

        <ChartCard
          title="By component"
          subtitle="Where defects cluster"
          table={<CountTable caption="By component" rows={data.by_component} />}
        >
          <BarChart data={toBars(data.by_component)} formatValue={formatNumber} labelWidth={130} />
        </ChartCard>
      </div>

      <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
        <ChartCard
          title="By root cause"
          subtitle="Tells you whether to fix the process or the code"
          table={<CountTable caption="By root cause" rows={data.by_root_cause} />}
        >
          <BarChart data={toBars(data.by_root_cause)} formatValue={formatNumber} labelWidth={130} />
        </ChartCard>

        <ChartCard
          title="Age of open defects"
          subtitle="The longer a defect stays open, the more it needs attention"
          table={<CountTable caption="Age of open defects" rows={data.ageing} />}
        >
          <BarChart
            data={toBars(data.ageing)}
            colors={[SEVERITY_COLORS[4], SEVERITY_COLORS[3], SEVERITY_COLORS[1], SEVERITY_COLORS[0]]}
            formatValue={formatNumber}
            labelWidth={100}
          />
        </ChartCard>
      </div>

      <section className="card">
        <div className="card-head">
          <h2>Recent defects</h2>
        </div>
        <p className="sub">JIRA issues created in the selected range, newest first.</p>
        <div className="scroll-x scroll-y">
          <table>
            <thead>
              <tr>
                <th>Key</th>
                <th>Summary</th>
                <th>Severity</th>
                <th>Component</th>
                <th>Found in</th>
                <th>Status</th>
                <th>Assignee</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.map((item) => (
                <tr key={item.key}>
                  <td className="mono">
                    {item.url ? (
                      <a href={item.url} target="_blank" rel="noreferrer">
                        {item.key}
                      </a>
                    ) : (
                      item.key
                    )}
                  </td>
                  <td>{item.summary}</td>
                  <td>{item.severity}</td>
                  <td>{item.component}</td>
                  <td>{PHASE_LABELS[item.found_phase] ?? item.found_phase}</td>
                  <td>{STATUS_LABELS[item.status_category] ?? item.status}</td>
                  <td className="muted">{item.assignee ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

function toBars(rows: NamedCount[], labels?: Record<string, string>) {
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  return rows.map((row) => ({
    name: labels?.[row.name] ?? row.name,
    value: row.count,
    note: total ? `${((row.count / total) * 100).toFixed(1)}%` : undefined,
  }))
}

function CountTable({
  caption,
  rows,
  labels,
}: {
  caption: string
  rows: NamedCount[]
  labels?: Record<string, string>
}) {
  const total = rows.reduce((sum, row) => sum + row.count, 0)
  return (
    <table>
      <caption>{caption}</caption>
      <thead>
        <tr>
          <th>Category</th>
          <th className="num">Count</th>
          <th className="num">Share</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.name}>
            <td>{labels?.[row.name] ?? row.name}</td>
            <td className="num">{row.count}</td>
            <td className="num">{total ? `${((row.count / total) * 100).toFixed(1)}%` : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
