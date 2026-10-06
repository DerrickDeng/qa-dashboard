/**
 * Horizontal bar chart for magnitude comparison.
 *
 * One series, one colour - a value ramp across nominal categories would burn the
 * colour channel on information the bar length already carries. Pass `colors`
 * only when the categories are genuinely ordered (severity, age buckets).
 */
import { Tooltip, useTooltip } from './primitives'

export interface BarDatum {
  name: string
  value: number
  note?: string
}

interface Props {
  data: BarDatum[]
  color?: string
  colors?: string[]
  formatValue: (value: number) => string
  barHeight?: number
  labelWidth?: number
  /** Fix the track length. Pass 100 for percentages, so a 91% bar reads as 91%
   *  of the whole and not as 95% of the largest bar. */
  max?: number
}

export function BarChart({
  data,
  color = 'var(--series-1)',
  colors,
  formatValue,
  barHeight = 20,
  labelWidth = 150,
  max: fixedMax,
}: Props) {
  const { tooltip, show, hide } = useTooltip()
  if (data.length === 0) return <p className="empty">No data in this range</p>

  const width = 620
  const gap = 10
  const rowHeight = barHeight + gap
  const height = data.length * rowHeight + 6
  const valueWidth = 64
  const trackWidth = width - labelWidth - valueWidth
  const max = fixedMax ?? Math.max(...data.map((item) => item.value), 1)

  return (
    <>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img">
        {data.map((item, index) => {
          const y = index * rowHeight + 3
          const barWidth = Math.max(2, (item.value / max) * trackWidth)
          const fill = colors ? colors[Math.min(index, colors.length - 1)] : color
          return (
            <g
              key={item.name}
              onMouseMove={(event) =>
                show({
                  x: event.clientX,
                  y: event.clientY,
                  title: item.name,
                  rows: [
                    { label: 'Count', value: formatValue(item.value), color: fill },
                    ...(item.note ? [{ label: 'Share', value: item.note }] : []),
                  ],
                })
              }
              onMouseLeave={hide}
            >
              {/* Full-row hit area, so the target is far bigger than the bar. */}
              <rect x={0} y={y - gap / 2} width={width} height={rowHeight} fill="transparent" />
              <text
                x={labelWidth - 10}
                y={y + barHeight / 2 + 4}
                textAnchor="end"
                fontSize={12}
                fill="var(--text-secondary)"
              >
                {item.name.length > 20 ? `${item.name.slice(0, 19)}…` : item.name}
              </text>
              {/* 4px rounded data-end, square at the baseline. */}
              <path
                d={roundedRightEnd(labelWidth, y, barWidth, barHeight, 4)}
                fill={fill}
              />
              <text
                x={labelWidth + barWidth + 8}
                y={y + barHeight / 2 + 4}
                fontSize={12}
                fill="var(--text-secondary)"
                style={{ fontVariantNumeric: 'tabular-nums' }}
              >
                {formatValue(item.value)}
              </text>
            </g>
          )
        })}
      </svg>
      <Tooltip state={tooltip} />
    </>
  )
}

/** A bar with square corners at the baseline and a 4px radius at the data end. */
function roundedRightEnd(x: number, y: number, width: number, height: number, radius: number) {
  const r = Math.min(radius, width)
  return [
    `M ${x} ${y}`,
    `H ${x + width - r}`,
    `Q ${x + width} ${y} ${x + width} ${y + r}`,
    `V ${y + height - r}`,
    `Q ${x + width} ${y + height} ${x + width - r} ${y + height}`,
    `H ${x}`,
    'Z',
  ].join(' ')
}
