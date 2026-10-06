import type { ReactNode } from 'react'

/** The single number a view leads with. Exactly one per page. */
export function Hero({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note?: ReactNode
}) {
  return (
    <section className="card hero">
      <span className="hero-label">{label}</span>
      <span className="hero-value">{value}</span>
      {note && <span className="hero-delta">{note}</span>}
    </section>
  )
}

export function StatTile({
  label,
  value,
  note,
  color,
}: {
  label: string
  value: string
  note?: ReactNode
  color?: string
}) {
  return (
    <section className="card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={color ? { color } : undefined}>
        {value}
      </div>
      {note && <div className="stat-note">{note}</div>}
    </section>
  )
}
