import { useCallback, useEffect, useState } from 'react'
import { api, setUnauthorizedHandler } from './api/client'
import type {
  AiSection,
  DefectSection,
  ExecutionSection,
  FilterOptions,
  SessionUser,
  Slice,
} from './api/types'
import { FilterRow } from './components/FilterRow'
import { AiPage } from './pages/AiPage'
import { DefectPage } from './pages/DefectPage'
import { ExecutionPage } from './pages/ExecutionPage'
import { LoginPage } from './pages/LoginPage'
import { RunReportPage } from './pages/RunReportPage'

type Tab = 'execution' | 'defects' | 'ai'

const TABS: { id: Tab; label: string }[] = [
  { id: 'execution', label: 'Test execution' },
  { id: 'defects', label: 'Defects' },
  { id: 'ai', label: 'AI effectiveness' },
]

const INITIAL_SLICE: Slice = { days: 14, application_code: '', region: '', environment: '' }

type AuthState =
  | { status: 'checking' }
  | { status: 'signed-out'; notice?: string }
  | { status: 'signed-in'; user: SessionUser }

export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'checking' })

  useEffect(() => {
    let active = true
    api
      .currentSession()
      .then((user) => active && setAuth({ status: 'signed-in', user }))
      .catch(() => active && setAuth({ status: 'signed-out' }))
    return () => {
      active = false
    }
  }, [])

  // A 401 on any request means the session ended - it expired, the password
  // changed, or the account was disabled - so go back to sign-in and say why.
  useEffect(() => {
    setUnauthorizedHandler(() =>
      setAuth((current) =>
        current.status === 'signed-in'
          ? { status: 'signed-out', notice: 'Your session has ended. Sign in again to continue.' }
          : current,
      ),
    )
    return () => setUnauthorizedHandler(null)
  }, [])

  const signOut = useCallback(async () => {
    await api.logout().catch(() => undefined)
    setAuth({ status: 'signed-out' })
  }, [])

  if (auth.status === 'checking') {
    return <div className="auth-screen" aria-busy="true" />
  }

  if (auth.status === 'signed-out') {
    return (
      <LoginPage
        notice={auth.notice}
        onSignedIn={(user) => setAuth({ status: 'signed-in', user })}
      />
    )
  }

  return <Dashboard user={auth.user} onSignOut={() => void signOut()} />
}

function Dashboard({ user, onSignOut }: { user: SessionUser; onSignOut: () => void }) {
  const [tab, setTab] = useState<Tab>('execution')
  const [slice, setSlice] = useState<Slice>(INITIAL_SLICE)
  const [options, setOptions] = useState<FilterOptions | null>(null)
  const [openRunId, setOpenRunId] = useState<string | null>(null)

  const [execution, setExecution] = useState<ExecutionSection | null>(null)
  const [defects, setDefects] = useState<DefectSection | null>(null)
  const [ai, setAi] = useState<AiSection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.filters().then(setOptions).catch(() => setOptions(null))
  }, [])

  // Each slice change starts a new load. A slower response to an earlier slice
  // must not overwrite a newer one, so only the latest effect may apply results.
  useEffect(() => {
    let active = true
    setLoading(true)
    setError(null)
    Promise.all([api.execution(slice), api.defects(slice), api.ai(slice)])
      .then(([nextExecution, nextDefects, nextAi]) => {
        if (!active) return
        setExecution(nextExecution)
        setDefects(nextDefects)
        setAi(nextAi)
      })
      .catch((caught) => {
        if (!active) return
        setError(caught instanceof Error ? caught.message : 'Failed to load the dashboard.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [slice])

  return (
    <>
      <header className="topbar">
        <h1>QA Dashboard</h1>
        <nav className="tabs" aria-label="Sections">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              aria-current={tab === item.id && !openRunId ? 'page' : undefined}
              onClick={() => {
                setTab(item.id)
                setOpenRunId(null)
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="account">
          <span className="account-name">{user.username}</span>
          <button type="button" className="link-button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
      </header>

      {!openRunId && <FilterRow
          slice={slice}
          options={options}
          onChange={(patch) => setSlice((current) => ({ ...current, ...patch }))}
        />}

      {/* Hold the previous render while refetching, so nothing jumps. */}
      <main style={{ opacity: loading && execution ? 0.55 : 1, transition: 'opacity 120ms' }}>
        {error && <div className="banner">{error}</div>}

        {openRunId ? (
          <RunReportPage runId={openRunId} onBack={() => setOpenRunId(null)} />
        ) : loading && !execution ? (
          <p className="empty">Loading…</p>
        ) : (
          <>
            {tab === 'execution' && execution && (
              <ExecutionPage data={execution} onOpenRun={setOpenRunId} />
            )}
            {tab === 'defects' && defects && <DefectPage data={defects} />}
            {tab === 'ai' && ai && <AiPage data={ai} />}
          </>
        )}
      </main>
    </>
  )
}
