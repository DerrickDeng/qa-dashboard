/**
 * Multi-series line chart. One shared y-axis - never two scales on one plot.
 * Hover shows a crosshair and every series at that x.
 */
import { Legend, Tooltip, niceTicksRange, useTooltip } from './primitives'

export interface LineSeries {
  key: string
  label: string
  color: string
  values: (number | null)[]
}

interface Props {
  labels: string[]
  series: LineSeries[]
  height?: number
  yMax?: number
  /** Set when the values live in a narrow band near the top (a pass rate, say),
   *  where a 0-based axis would flatten every difference worth seeing. */
  yMin?: number
  formatValue: (value: number) => string
  formatTick?: (value: number) => string
}

const PAD = { top: 12, right: 14, bottom: 26, left: 46 }

export function LineChart({
  labels,
  series,
  height = 210,
  yMax,
  yMin,
  formatValue,
  formatTick,
}: Props) {
  const { tooltip, show, hide } = useTooltip()
  const width = 640
  const plotWidth = width - PAD.left - PAD.right
  const plotHeight = height - PAD.top - PAD.bottom

  const values = series.flatMap((item) => item.values.filter((v): v is number => v !== null))
  const dataMax = values.length ? Math.max(...values) : 0.0001
  const dataMin = values.length ? Math.min(...values) : 0
  const ticks = niceTicksRange(yMin ?? 0, yMax ?? dataMax, 4)
  const bottom = ticks[0]
  const top = Math.max(ticks[ticks.length - 1], yMax ?? dataMax)
  void dataMin

  const x = (index: number) =>
    PAD.left + (labels.length <= 1 ? plotWidth / 2 : (index / (labels.length - 1)) * plotWidth)
  const y = (value: number) =>
    PAD.top + plotHeight - ((value - bottom) / (top - bottom || 1)) * plotHeight

  const tickEvery = Math.max(1, Math.ceil(labels.length / 8))

  function onMove(event: React.MouseEvent<SVGRectElement>) {
    const box = event.currentTarget.getBoundingClientRect()
    const ratio = (event.clientX - box.left) / box.width
    const index = Math.round(ratio * (labels.length - 1))
    if (index < 0 || index >= labels.length) return
    show({
      x: event.clientX,
      y: event.clientY,
      title: labels[index],
      rows: series.map((item) => ({
        label: item.label,
        color: item.color,
        value: item.values[index] === null ? '—' : formatValue(item.values[index] as number),
      })),
    })
  }

  const hovered = tooltip ? labels.indexOf(tooltip.title) : -1

  return (
    <>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={series.map((s) => s.label).join(', ')}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--gridline)"
              strokeWidth={1}
            />
            <text
              x={PAD.left - 7}
              y={y(tick) + 3.5}
              textAnchor="end"
              fontSize={10}
              fill="var(--text-muted)"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {(formatTick ?? formatValue)(tick)}
            </text>
          </g>
        ))}

        {labels.map((label, index) =>
          index % tickEvery === 0 ? (
            <text
              key={label}
              x={x(index)}
              y={height - 8}
              textAnchor="middle"
              fontSize={10}
              fill="var(--text-muted)"
            >
              {label}
            </text>
          ) : null,
        )}

        {hovered >= 0 && (
          <line
            x1={x(hovered)}
            x2={x(hovered)}
            y1={PAD.top}
            y2={PAD.top + plotHeight}
            stroke="var(--baseline)"
            strokeWidth={1}
          />
        )}

        {series.map((item) => {
          const points = item.values
            .map((value, index) => (value === null ? null : `${x(index)},${y(value)}`))
            .filter((point): point is string => point !== null)
          if (points.length === 0) return null
          return (
            <g key={item.key}>
              <polyline
                points={points.join(' ')}
                fill="none"
                stroke={item.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              {hovered >= 0 && item.values[hovered] !== null && (
                <circle
                  cx={x(hovered)}
                  cy={y(item.values[hovered] as number)}
                  r={4.5}
                  fill={item.color}
                  stroke="var(--surface-1)"
                  strokeWidth={2}
                />
              )}
            </g>
          )
        })}

        <line
          x1={PAD.left}
          x2={width - PAD.right}
          y1={y(bottom)}
          y2={y(bottom)}
          stroke="var(--baseline)"
          strokeWidth={1}
        />

        <rect
          x={PAD.left}
          y={PAD.top}
          width={plotWidth}
          height={plotHeight}
          fill="transparent"
          onMouseMove={onMove}
          onMouseLeave={hide}
        />
      </svg>
      {series.length > 1 && (
        <Legend items={series.map((item) => ({ label: item.label, color: item.color }))} />
      )}
      <Tooltip state={tooltip} />
    </>
  )
}
