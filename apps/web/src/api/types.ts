export type TestStatus = 'passed' | 'failed' | 'flaky' | 'skipped'

export interface Slice {
  days: number
  application_code: string
  region: string
  environment: string
}

export interface FilterOptions {
  application_codes: string[]
  regions: string[]
  environments: string[]
  agents: string[]
  models: string[]
  prompt_versions: string[]
}

export interface ExecutionSummary {
  day: string | null
  runs: number
  total: number
  passed: number
  failed: number
  flaky: number
  skipped: number
  pass_rate: number | null
  previous_pass_rate: number | null
}

export interface TrendPoint {
  date: string
  total: number
  passed: number
  failed: number
  flaky: number
  skipped: number
  pass_rate: number | null
}

export interface ProjectRow {
  project: string
  total: number
  passed: number
  failed: number
  flaky: number
  skipped: number
  pass_rate: number | null
}

export interface RunRow {
  id: string
  started_at: string
  duration_ms: number
  application_code: string
  region: string
  environment: string
  product_type: string
  job_name: string | null
  build_number: string | null
  branch: string | null
  commit_sha: string | null
  ci_url: string | null
  total: number
  passed: number
  failed: number
  flaky: number
  skipped: number
  pass_rate: number | null
  has_bundle: boolean
}

export interface FailureRow {
  test_key: string
  title: string
  feature: string
  project: string
  runs: number
  failures: number
  failure_rate: number | null
  error_message: string | null
}

export interface FlakyRow {
  test_key: string
  title: string
  feature: string
  project: string
  file: string
  runs: number
  flaky_runs: number
  failed_runs: number
  flips: number
  retries: number
  flaky_score: number
  last_error: string | null
  recent: TestStatus[]
}

export interface ExecutionSection {
  summary: ExecutionSummary
  trend: TrendPoint[]
  by_project: ProjectRow[]
  runs: RunRow[]
  top_failures: FailureRow[]
  flaky_ranking: FlakyRow[]
  flaky_trend: { date: string; flaky: number; executed: number; flaky_rate: number | null }[]
}

export interface NamedCount {
  name: string
  count: number
}

export interface DefectSection {
  summary: {
    created: number
    resolved: number
    open: number
    open_critical: number
    escape_rate: number | null
    escaped: number
    total: number
    mttr_days: number | null
  }
  trend: { date: string; created: number; resolved: number; open: number }[]
  by_severity: NamedCount[]
  by_component: NamedCount[]
  by_found_phase: NamedCount[]
  by_status: NamedCount[]
  by_root_cause: NamedCount[]
  ageing: NamedCount[]
  recent: {
    key: string
    summary: string
    severity: string
    component: string
    found_phase: string
    status: string
    status_category: string
    assignee: string | null
    created_at: string
    resolved_at: string | null
    url: string | null
  }[]
}

export interface AiDimensionRow {
  name: string
  runs: number
  generated: number
  accepted: number
  adoption: number | null
  adoption_unchanged: number | null
  precision: number | null
  recall: number | null
  f1: number | null
  hallucination_rate: number | null
  cost_usd: number
}

export interface AiSection {
  summary: {
    runs: number
    generated: number
    accepted: number
    accepted_unchanged: number
    adoption: number | null
    adoption_unchanged: number | null
    avg_edit_distance: number | null
    golden_total: number
    matched: number
    missing: number
    extra: number
    hallucinated: number
    precision: number | null
    recall: number | null
    f1: number | null
    hallucination_rate: number | null
    cost_usd: number
    tokens: number
    cost_per_accepted: number | null
  }
  trend: {
    date: string
    generated: number
    accepted: number
    adoption: number | null
    adoption_unchanged: number | null
    precision: number | null
    recall: number | null
    f1: number | null
  }[]
  by_agent: AiDimensionRow[]
  by_model: AiDimensionRow[]
  by_prompt_version: AiDimensionRow[]
  recent: {
    id: string
    agent: string
    model: string
    prompt_version: string
    input_ref: string
    started_at: string
    duration_ms: number
    generated: number
    accepted: number
    accepted_unchanged: number
    adoption: number | null
    matched: number
    missing: number
    extra: number
    hallucinated: number
    golden_total: number
    precision: number | null
    recall: number | null
    cost_usd: number
  }[]
}

export interface RunDetail extends RunRow {
  bundle_url: string | null
  report: unknown
}

export interface SessionUser {
  username: string
}
