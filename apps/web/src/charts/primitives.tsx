/**
 * Shared chart pieces, hand-drawn in SVG so the mark specs are exact:
 * 2px lines, >=8px markers with a 2px surface ring, bars capped at 24px with a
 * 4px rounded data-end, hairline solid gridlines, and a 2px surface gap between
 * touching fills.
 */
import { useCallback, useState, type ReactNode } from 'react'

export interface TooltipRow {
  label: string
  value: string
  color?: string
}

export interface TooltipState {
  x: number
  y: number
  title: string
  rows: TooltipRow[]
}

export function useTooltip() {
  const [tooltip, setTooltip] = useState<TooltipState | null>(null)
  const show = useCallback((next: TooltipState) => setTooltip(next), [])
  const hide = useCallback(() => setTooltip(null), [])
  return { tooltip, show, hide }
}

export function Tooltip({ state }: { state: TooltipState | null }) {
  if (!state) return null
  // Nudge away from the cursor so the pointer never covers the readout.
  const style = { left: Math.min(state.x + 14, window.innerWidth - 260), top: state.y + 14 }
  return (
    <div className="chart-tooltip" style={style} role="presentation">
      <div className="t-title">{state.title}</div>
      {state.rows.map((row) => (
        <div className="t-row" key={row.label}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
            {row.color && (
              <i
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: 2,
                  background: row.color,
                  display: 'inline-block',
                }}
              />
            )}
            {row.label}
          </span>
          <b>{row.value}</b>
        </div>
      ))}
    </div>
  )
}

export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="legend">
      {items.map((item) => (
        <span key={item.label}>
          <i style={{ background: item.color }} />
          {item.label}
        </span>
      ))}
    </div>
  )
}

/** A card that can flip between its chart and the equivalent table. */
export function ChartCard({
  title,
  subtitle,
  table,
  children,
}: {
  title: string
  subtitle?: string
  table: ReactNode
  children: ReactNode
}) {
  const [showTable, setShowTable] = useState(false)
  return (
    <section className="card">
      <div className="card-head">
        <h2>{title}</h2>
        <button
          type="button"
          className="link-button"
          onClick={() => setShowTable((value) => !value)}
          aria-pressed={showTable}
        >
          {showTable ? 'Show chart' : 'Show table'}
        </button>
      </div>
      {subtitle && <p className="sub">{subtitle}</p>}
      {showTable ? <div className="scroll-x scroll-y">{table}</div> : children}
    </section>
  )
}

export function EmptyState({ message }: { message: string }) {
  return <p className="empty">{message}</p>
}

export const formatPercent = (value: number | null | undefined, digits = 1): string =>
  value === null || value === undefined ? '—' : `${(value * 100).toFixed(digits)}%`

export const formatNumber = (value: number | null | undefined): string =>
  value === null || value === undefined ? '—' : value.toLocaleString('en-US')

export const shortDate = (iso: string): string => iso.slice(5).replace('-', '/')

/** Clean axis ticks spanning min..max, rounded to readable steps. */
export function niceTicksRange(min: number, max: number, count = 4): number[] {
  if (max <= min) return [min]
  const raw = (max - min) / count
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? magnitude * 10
  const start = Math.floor(min / step) * step
  const ticks: number[] = []
  for (let value = start; value <= max + step / 2; value += step) {
    ticks.push(Number(value.toFixed(6)))
  }
  return ticks
}

/** Clean axis ticks for a 0..max range. */
export function niceTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0]
  const raw = max / count
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? magnitude * 10
  const ticks: number[] = []
  for (let value = 0; value <= max + step / 2; value += step) ticks.push(Number(value.toFixed(6)))
  return ticks
}
