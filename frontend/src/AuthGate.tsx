import { FormEvent, ReactNode, useCallback, useEffect, useState } from 'react'
import { checkSession, createSession, UNAUTHORIZED_EVENT } from './api'

type GateState = 'checking' | 'ok' | 'locked'

/**
 * Remove the one-time login token from the address bar, so that it does not
 * stay in the browser history or get copied with the URL.
 */
function takeTokenFromUrl(): string | null {
  const url = new URL(window.location.href)
  const token = url.searchParams.get('token')
  if (token === null) return null
  url.searchParams.delete('token')
  window.history.replaceState(window.history.state, '', url.pathname + url.search + url.hash)
  return token
}

// Read once at module load. React StrictMode runs effects twice in
// development, and the first run must not lose the token for the second.
const initialUrlToken = takeTokenFromUrl()

export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>('checking')
  const [tokenInput, setTokenInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    let cancelled = false
    const run = async () => {
      const urlToken = initialUrlToken
      if (urlToken) {
        const ok = await createSession(urlToken)
        if (!ok && !cancelled) setError('The login link is not valid. Run `ralphx dashboard-url` to get a new one.')
      }
      const authenticated = await checkSession()
      if (!cancelled) setState(authenticated ? 'ok' : 'locked')
    }
    run()
    return () => {
      cancelled = true
    }
  }, [])

  const lock = useCallback(() => setState('locked'), [])
  useEffect(() => {
    window.addEventListener(UNAUTHORIZED_EVENT, lock)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, lock)
  }, [lock])

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    const ok = await createSession(tokenInput.trim())
    setSubmitting(false)
    if (ok) {
      setTokenInput('')
      setState('ok')
    } else {
      setError('The token is not valid.')
    }
  }

  if (state === 'ok') return <>{children}</>
  if (state === 'checking') {
    return <div className="min-h-screen bg-gray-900" aria-busy="true" />
  }

  return (
    <main className="min-h-screen bg-gray-900 text-gray-100 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <h1 className="text-xl font-semibold mb-3">Log in to RalphX</h1>
        <p className="text-sm text-gray-300 mb-2">
          This dashboard controls your Claude accounts and project files, so it needs your local access token.
        </p>
        <p className="text-sm text-gray-300 mb-5">
          Open the login link that <code className="text-gray-100">ralphx serve</code> prints. To get the link again, run{' '}
          <code className="text-gray-100">ralphx dashboard-url</code>. You can also paste the token below.
        </p>
        <form onSubmit={onSubmit} className="space-y-3">
          <label htmlFor="ralphx-token" className="block text-sm text-gray-300">
            Access token
          </label>
          <input
            id="ralphx-token"
            type="password"
            autoComplete="off"
            value={tokenInput}
            onChange={(e) => setTokenInput(e.target.value)}
            className="w-full rounded-md bg-gray-800 border border-gray-600 px-3 py-2 text-gray-100 focus:outline-none focus:border-gray-400"
          />
          {error && (
            <p role="alert" className="text-sm text-red-300">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={submitting || tokenInput.trim() === ''}
            className="rounded-md bg-gray-100 text-gray-900 px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            {submitting ? 'Checking...' : 'Log in'}
          </button>
        </form>
      </div>
    </main>
  )
}
