/** The one place the dashboard talks to the API. */
import type {
  AiSection,
  DefectSection,
  ExecutionSection,
  FilterOptions,
  RunDetail,
  SessionUser,
  Slice,
} from './types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number
  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

let unauthorizedHandler: (() => void) | null = null

/** The app registers this, so a session that ends mid-use returns to sign-in. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

function query(slice: Slice): string {
  const params = new URLSearchParams({ days: String(slice.days) })
  if (slice.application_code) params.set('application_code', slice.application_code)
  if (slice.region) params.set('region', slice.region)
  if (slice.environment) params.set('environment', slice.environment)
  return params.toString()
}

interface RequestOptions extends RequestInit {
  /** Sign-in and the first session check expect a 401 and handle it themselves. */
  expectUnauthorized?: boolean
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { expectUnauthorized = false, headers, ...init } = options

  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      // The session is an HttpOnly cookie; it has to travel with every request.
      credentials: 'include',
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init.body ? { 'Content-Type': 'application/json' } : {}),
        ...(headers as Record<string, string> | undefined),
      },
    })
  } catch {
    throw new ApiError('Cannot reach the dashboard API.', 0)
  }

  if (response.status === 401 && !expectUnauthorized) {
    unauthorizedHandler?.()
  }
  if (response.status === 204) {
    return undefined as T
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
    const detail = typeof body?.detail === 'string' ? body.detail : null
    throw new ApiError(detail ?? `Request failed (${response.status})`, response.status)
  }
  return (await response.json()) as T
}

export const api = {
  currentSession: () => request<SessionUser>('/api/v1/session', { expectUnauthorized: true }),
  login: (username: string, password: string) =>
    request<SessionUser>('/api/v1/session', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      expectUnauthorized: true,
    }),
  logout: () => request<void>('/api/v1/session', { method: 'DELETE', expectUnauthorized: true }),

  filters: () => request<FilterOptions>('/api/v1/filters'),
  execution: (slice: Slice) => request<ExecutionSection>(`/api/v1/execution?${query(slice)}`),
  defects: (slice: Slice) => request<DefectSection>(`/api/v1/defects?${query(slice)}`),
  ai: (slice: Slice) => request<AiSection>(`/api/v1/ai?${query(slice)}`),
  run: (runId: string) => request<RunDetail>(`/api/v1/runs/${encodeURIComponent(runId)}`),
}
