import type { FilterOptions, Slice } from '../api/types'

interface Props {
  slice: Slice
  options: FilterOptions | null
  // Only the changed fields, merged into the latest slice by the owner: two
  // quick changes must not overwrite each other with a stale copy.
  onChange: (patch: Partial<Slice>) => void
}

const WINDOWS = [
  { value: 7, label: 'Last 7 days' },
  { value: 14, label: 'Last 14 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
]

/** One filter row above everything it scopes; all three tabs use the same slice. */
export function FilterRow({ slice, options, onChange }: Props) {
  return (
    <div className="filter-row">
      <label htmlFor="filter-days">
        Date range
        <select
          id="filter-days"
          value={slice.days}
          onChange={(event) => onChange({ days: Number(event.target.value) })}
        >
          {WINDOWS.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
      </label>

      <Picker
        id="filter-app"
        label="Application"
        value={slice.application_code}
        values={options?.application_codes ?? []}
        onChange={(value) => onChange({ application_code: value })}
      />
      <Picker
        id="filter-region"
        label="Region"
        value={slice.region}
        values={options?.regions ?? []}
        onChange={(value) => onChange({ region: value })}
      />
      <Picker
        id="filter-env"
        label="Environment"
        value={slice.environment}
        values={options?.environments ?? []}
        onChange={(value) => onChange({ environment: value })}
      />
    </div>
  )
}

function Picker({
  id,
  label,
  value,
  values,
  onChange,
}: {
  id: string
  label: string
  value: string
  values: string[]
  onChange: (value: string) => void
}) {
  return (
    <label htmlFor={id}>
      {label}
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {values.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  )
}
