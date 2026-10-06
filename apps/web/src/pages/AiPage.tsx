import { LineChart } from '../charts/LineChart'
import { ChartCard, formatNumber, formatPercent, shortDate } from '../charts/primitives'
import { Hero, StatTile } from '../components/Tiles'
import type { AiDimensionRow, AiSection } from '../api/types'

export function AiPage({ data }: { data: AiSection }) {
  const { summary, trend } = data

  return (
    <>
      <div className="banner">
        <b>These two numbers answer different questions.</b> Adoption asks whether a person kept
        the output, and comes from the review record. Accuracy asks whether the output was right,
        by comparison with reviewed Golden tests. Without a Golden set there is no accuracy.
      </div>

      <div className="grid grid-kpi" style={{ marginBottom: '1rem' }}>
        <Hero
          label="Adoption"
          value={formatPercent(summary.adoption)}
          note={`${formatNumber(summary.accepted)} of ${formatNumber(summary.generated)} items accepted; ${formatPercent(summary.adoption_unchanged)} kept unchanged`}
        />
        <StatTile
          label="Accuracy (F1)"
          value={formatPercent(summary.f1)}
          note={`Precision ${formatPercent(summary.precision)} · recall ${formatPercent(summary.recall)}`}
        />
        <StatTile
          label="Unchanged adoption"
          value={formatPercent(summary.adoption_unchanged)}
          note={`Edited items changed ${summary.avg_edit_distance?.toFixed(0) ?? '—'} characters on average`}
        />
        <StatTile
          label="Hallucination rate"
          value={formatPercent(summary.hallucination_rate)}
          note={`${summary.hallucinated} items referenced behaviour that does not exist`}
          color={(summary.hallucination_rate ?? 0) > 0.1 ? 'var(--status-critical)' : undefined}
        />
        <StatTile
          label="Cost"
          value={`$${summary.cost_usd.toFixed(2)}`}
          note={`$${summary.cost_per_accepted?.toFixed(4) ?? '—'} per accepted item · ${formatNumber(summary.tokens)} tokens`}
        />
      </div>

      <div className="grid grid-2" style={{ marginBottom: '1rem' }}>
        <ChartCard
          title="Adoption trend"
          subtitle="The gap between the lines is output that was kept but had to be rewritten"
          table={
            <table>
              <caption>Adoption trend</caption>
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num">Generated</th>
                  <th className="num">Accepted</th>
                  <th className="num">Adoption</th>
                  <th className="num">Unchanged</th>
                </tr>
              </thead>
              <tbody>
                {trend.map((point) => (
                  <tr key={point.date}>
                    <td>{point.date}</td>
                    <td className="num">{point.generated}</td>
                    <td className="num">{point.accepted}</td>
                    <td className="num">{formatPercent(point.adoption)}</td>
                    <td className="num">{formatPercent(point.adoption_unchanged)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          <LineChart
            labels={trend.map((point) => shortDate(point.date))}
            series={[
              { key: 'adoption', label: 'Adoption', color: 'var(--series-1)', values: trend.map((p) => p.adoption) },
              {
                key: 'unchanged',
                label: 'Unchanged adoption',
                color: 'var(--series-3)',
                values: trend.map((p) => p.adoption_unchanged),
              },
            ]}
            yMax={1}
            formatValue={(value) => formatPercent(value)}
            formatTick={(value) => `${Math.round(value * 100)}%`}
          />
        </ChartCard>

        <ChartCard
          title="Accuracy trend"
          subtitle="Precision and recall kept apart: a single number hides the failure mode"
          table={
            <table>
              <caption>Accuracy trend</caption>
              <thead>
                <tr>
                  <th>Date</th>
                  <th className="num">Precision</th>
                  <th className="num">Recall</th>
                  <th className="num">F1</th>
                </tr>
              </thead>
              <tbody>
                {trend.map((point) => (
                  <tr key={point.date}>
                    <td>{point.date}</td>
                    <td className="num">{formatPercent(point.precision)}</td>
                    <td className="num">{formatPercent(point.recall)}</td>
                    <td className="num">{formatPercent(point.f1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          }
        >
          <LineChart
            labels={trend.map((point) => shortDate(point.date))}
            series={[
              { key: 'precision', label: 'Precision', color: 'var(--series-1)', values: trend.map((p) => p.precision) },
              { key: 'recall', label: 'Recall', color: 'var(--series-2)', values: trend.map((p) => p.recall) },
            ]}
            yMax={1}
            formatValue={(value) => formatPercent(value)}
            formatTick={(value) => `${Math.round(value * 100)}%`}
          />
        </ChartCard>
      </div>

      <div className="grid grid-3" style={{ marginBottom: '1rem' }}>
        <DimensionCard title="By agent" subtitle="Whose output people keep" rows={data.by_agent} />
        <DimensionCard title="By model" subtitle="Whether switching models helped" rows={data.by_model} />
        <DimensionCard
          title="By prompt version"
          subtitle="A regression check after a prompt change"
          rows={data.by_prompt_version}
        />
      </div>

      <section className="card">
        <div className="card-head">
          <h2>Recent agent runs</h2>
        </div>
        <p className="sub">Each row is one generation plus one human review.</p>
        <div className="scroll-x scroll-y">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Agent</th>
                <th>Model</th>
                <th>Prompt</th>
                <th>Input</th>
                <th className="num">Accepted</th>
                <th className="num">Adoption</th>
                <th className="num">Matched / Golden</th>
                <th className="num">Extra</th>
                <th className="num">Hallucinated</th>
                <th className="num">Cost</th>
              </tr>
            </thead>
            <tbody>
              {data.recent.map((run) => (
                <tr key={run.id}>
                  <td className="mono">{run.started_at.replace('T', ' ').slice(0, 16)}</td>
                  <td>{run.agent}</td>
                  <td className="muted">{run.model}</td>
                  <td className="mono">{run.prompt_version}</td>
                  <td className="muted">{run.input_ref}</td>
                  <td className="num">
                    {run.accepted}/{run.generated}
                  </td>
                  <td className="num">{formatPercent(run.adoption)}</td>
                  <td className="num">
                    {run.matched}/{run.golden_total}
                  </td>
                  <td className="num">{run.extra}</td>
                  <td className="num">{run.hallucinated}</td>
                  <td className="num">${run.cost_usd.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}

function DimensionCard({
  title,
  subtitle,
  rows,
}: {
  title: string
  subtitle: string
  rows: AiDimensionRow[]
}) {
  return (
    <section className="card">
      <div className="card-head">
        <h2>{title}</h2>
      </div>
      <p className="sub">{subtitle}</p>
      <div className="scroll-x">
        <table>
          <thead>
            <tr>
              <th />
              <th className="num">Adoption</th>
              <th className="num">F1</th>
              <th className="num">Halluc.</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <td>
                  {row.name}
                  <div className="muted" style={{ fontSize: 12 }}>
                    {row.runs} runs · {row.generated} items
                  </div>
                </td>
                <td className="num">{formatPercent(row.adoption)}</td>
                <td className="num">{formatPercent(row.f1)}</td>
                <td className="num">{formatPercent(row.hallucination_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
