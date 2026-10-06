/**
 * Status rendering.
 *
 * The status palette is deliberately not colourblind-safe on its own, so every
 * status is shown as icon + label + colour. Colour never carries the meaning
 * alone here.
 */
import type { TestStatus } from '../api/types'

export const STATUS_STYLE: Record<TestStatus, { label: string; icon: string; color: string }> = {
  passed: { label: 'Passed', icon: '✓', color: 'var(--status-good)' },
  flaky: { label: 'Flaky', icon: '⚠', color: 'var(--status-warning)' },
  failed: { label: 'Failed', icon: '✕', color: 'var(--status-critical)' },
  skipped: { label: 'Skipped', icon: '–', color: 'var(--deemphasis)' },
}

export function StatusTag({ status }: { status: TestStatus }) {
  const style = STATUS_STYLE[status]
  return (
    <span className="status" style={{ color: style.color }}>
      <i aria-hidden="true">{style.icon}</i>
      <span style={{ color: 'var(--text-primary)' }}>{style.label}</span>
    </span>
  )
}

/** The last N runs of one test, oldest to newest. */
export function StatusSparkline({ statuses }: { statuses: TestStatus[] }) {
  return (
    <span className="spark-cell" title={statuses.map((s) => STATUS_STYLE[s].label).join(' → ')}>
      {statuses.map((status, index) => (
        <b key={`${status}-${index}`} style={{ background: STATUS_STYLE[status].color }} />
      ))}
    </span>
  )
}

export const SEVERITY_COLORS = [
  'var(--ordinal-1)',
  'var(--ordinal-2)',
  'var(--ordinal-3)',
  'var(--ordinal-4)',
  'var(--ordinal-5)',
]
