/**
 * A single horizontal part-to-whole bar, with a 2px surface gap between
 * segments so neighbours separate without a border.
 */
import { Legend, Tooltip, useTooltip } from './primitives'

export interface StackSegment {
  key: string
  label: string
  value: number
  color: string
  icon?: string
}

export function StackedBar({
  segments,
  height = 26,
}: {
  segments: StackSegment[]
  height?: number
}) {
  const { tooltip, show, hide } = useTooltip()
  const total = segments.reduce((sum, item) => sum + item.value, 0)
  if (total === 0) return <p className="empty">No data in this range</p>

  const width = 620
  const gap = 2
  const visible = segments.filter((item) => item.value > 0)
  const available = width - gap * Math.max(0, visible.length - 1)

  let offset = 0
  return (
    <>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img">
        {visible.map((item) => {
          const segmentWidth = (item.value / total) * available
          const x = offset
          offset += segmentWidth + gap
          return (
            <rect
              key={item.key}
              x={x}
              y={0}
              width={Math.max(1, segmentWidth)}
              height={height}
              rx={3}
              fill={item.color}
              onMouseMove={(event) =>
                show({
                  x: event.clientX,
                  y: event.clientY,
                  title: `${item.icon ?? ''} ${item.label}`.trim(),
                  rows: [
                    { label: 'Tests', value: item.value.toLocaleString('en-US'), color: item.color },
                    { label: 'Share', value: `${((item.value / total) * 100).toFixed(1)}%` },
                  ],
                })
              }
              onMouseLeave={hide}
            />
          )
        })}
      </svg>
      <Legend
        items={visible.map((item) => ({
          label: `${item.icon ?? ''} ${item.label} ${item.value}`.trim(),
          color: item.color,
        }))}
      />
      <Tooltip state={tooltip} />
    </>
  )
}
