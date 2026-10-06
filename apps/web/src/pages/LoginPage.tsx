import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { ApiError, api } from '../api/client'
import type { SessionUser } from '../api/types'

interface Props {
  /** Shown above the form, e.g. when a session has just ended. */
  notice?: string
  onSignedIn: (user: SessionUser) => void
}

export function LoginPage({ notice, onSignedIn }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [capsLock, setCapsLock] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const usernameRef = useRef<HTMLInputElement>(null)
  const passwordRef = useRef<HTMLInputElement>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (submitting) return

    if (!username.trim() || !password) {
      setError('Enter your username and password.')
      ;(username.trim() ? passwordRef : usernameRef).current?.focus()
      return
    }

    setSubmitting(true)
    setError(null)
    try {
      onSignedIn(await api.login(username.trim(), password))
    } catch (caught) {
      setError(messageFor(caught))
      // Keep the username; clear the password so the next attempt starts clean.
      setPassword('')
      passwordRef.current?.focus()
      setSubmitting(false)
    }
  }

  function trackCapsLock(event: KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState('CapsLock'))
  }

  return (
    <div className="auth-screen">
      <main className="auth-card" aria-labelledby="sign-in-title">
        <div className="auth-brand">
          <span className="auth-mark" aria-hidden="true">
            QA
          </span>
          <span className="auth-brand-name">QA Dashboard</span>
        </div>

        <h1 id="sign-in-title">Sign in</h1>
        <p className="auth-lede">Test execution, defects, and AI effectiveness in one place.</p>

        {notice && !error && (
          <div className="auth-message notice" role="status">
            {notice}
          </div>
        )}
        {error && (
          <div className="auth-message error" role="alert">
            <span className="auth-message-icon" aria-hidden="true">
              !
            </span>
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input
              ref={usernameRef}
              id="username"
              name="username"
              type="text"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoFocus
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              aria-invalid={error ? true : undefined}
            />
          </div>

          <div className="field">
            <label htmlFor="password">Password</label>
            <div className="password-row">
              <input
                ref={passwordRef}
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={trackCapsLock}
                onKeyUp={trackCapsLock}
                aria-invalid={error ? true : undefined}
                aria-describedby={capsLock ? 'caps-lock-hint' : undefined}
              />
              <button
                type="button"
                className="password-toggle"
                aria-controls="password"
                aria-pressed={showPassword}
                onClick={() => setShowPassword((value) => !value)}
              >
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
            {capsLock && (
              <span id="caps-lock-hint" className="field-hint">
                Caps Lock is on.
              </span>
            )}
          </div>

          <button type="submit" className="primary-button" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="auth-footnote">
          No account yet? Accounts are created from the command line with{' '}
          <code>make user-add NAME=&lt;name&gt;</code>.
        </p>
      </main>
    </div>
  )
}

function messageFor(caught: unknown): string {
  if (caught instanceof ApiError) {
    if (caught.status === 0) return 'Cannot reach the dashboard. Check that it is running.'
    return caught.message
  }
  return 'Sign-in failed. Try again.'
}
