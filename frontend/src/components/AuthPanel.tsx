import { useState, useEffect, useRef } from 'react'
import { getAuthStatus, startLogin, logoutAuth, AuthStatus } from '../api'

interface AuthPanelProps {
  projectPath?: string  // If provided, shows project-scoped auth
}

export default function AuthPanel({ projectPath }: AuthPanelProps) {
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [loginPending, setLoginPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedScope, setSelectedScope] = useState<'project' | 'global'>(
    projectPath ? 'project' : 'global'
  )
  const pollRef = useRef<number | null>(null)
  const timeoutRef = useRef<number | null>(null)

  const loadStatus = async () => {
    try {
      const s = await getAuthStatus(projectPath)
      setStatus(s)
      setError(null)
    } catch (e) {
      setError('Failed to check auth status')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStatus()
    const interval = setInterval(loadStatus, 5000)
    return () => {
      clearInterval(interval)
      if (pollRef.current) clearInterval(pollRef.current)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [projectPath])

  const handleLogin = async () => {
    setLoginPending(true)
    setError(null)
    const scope = projectPath && selectedScope === 'project' ? 'project' : 'global'

    try {
      const result = await startLogin({ scope, project_path: projectPath })
      if (!result.success) {
        setError(result.error || 'Failed to start login')
        setLoginPending(false)
        return
      }

      // Poll for login completion (backend stores credentials automatically)
      pollRef.current = window.setInterval(async () => {
        try {
          const s = await getAuthStatus(projectPath)
          // OAuth flow stores credentials automatically, so just check if connected
          if (s.connected && !s.is_expired) {
            setStatus(s)
            if (pollRef.current) clearInterval(pollRef.current)
            if (timeoutRef.current) clearTimeout(timeoutRef.current)
            setLoginPending(false)
          }
        } catch {
          // Ignore polling errors
        }
      }, 1000)

      // Timeout after 2 minutes
      timeoutRef.current = window.setTimeout(() => {
        if (pollRef.current) clearInterval(pollRef.current)
        setLoginPending(false)
        setError('Login timed out. Please try again.')
      }, 120000)
    } catch (e) {
      setError('Failed to start login')
      setLoginPending(false)
    }
  }

  const handleLogout = async () => {
    try {
      const scope = status?.scope || 'global'
      await logoutAuth({ scope, project_path: projectPath })
      await loadStatus()
    } catch {
      setError('Failed to logout')
    }
  }

  const formatExpiry = (seconds?: number): string => {
    if (!seconds) return 'Unknown'
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    if (hours > 0) return `${hours}h ${mins}m`
    return `${mins}m`
  }

  if (loading) {
    return (
      <div className="bg-gray-800 rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="h-4 bg-gray-700 rounded w-1/2"></div>
      </div>
    )
  }

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h3 className="text-lg font-semibold mb-4 text-white">Claude Authentication</h3>

      {error && (
        <div className="mb-4 p-3 bg-red-900/50 border border-red-700 rounded text-red-200 text-sm">
          {error}
        </div>
      )}

      {status?.connected && !status?.is_expired ? (
        <div className="space-y-3">
          {/* Account email */}
          {status.email && (
            <p className="text-gray-300 text-sm">
              Logged in as <span className="text-white font-medium">{status.email}</span>
            </p>
          )}

          {/* Connection status with fallback indicator */}
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 bg-green-500 rounded-full" />
            <span className="text-green-400">Connected</span>
            {status.using_global_fallback ? (
              <span className="text-yellow-400 text-sm">(Using Global Account)</span>
            ) : (
              <span className="text-gray-500 text-sm">
                ({status.scope === 'project' ? 'Project' : 'Global'})
              </span>
            )}
          </div>

          {/* Override button when using global fallback on a project */}
          {status.using_global_fallback && projectPath && (
            <div className="mt-3 p-3 bg-gray-700/50 rounded border border-gray-600">
              <p className="text-gray-400 text-sm mb-2">
                This project is using your global Claude account.
              </p>
              <button
                onClick={() => {
                  setSelectedScope('project')
                  handleLogin()
                }}
                className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors disabled:opacity-50"
                disabled={loginPending}
              >
                {loginPending ? 'Waiting...' : 'Use Different Account for This Project'}
              </button>
            </div>
          )}

          {status.subscription_type && (
            <p className="text-gray-400 text-sm">
              Plan: <span className="text-white capitalize">{status.subscription_type}</span>
            </p>
          )}

          {status.rate_limit_tier && (
            <p className="text-gray-400 text-sm">
              Tier: <span className="text-white">{status.rate_limit_tier}</span>
            </p>
          )}

          <p className="text-gray-400 text-sm">
            Expires in: <span className="text-white">{formatExpiry(status.expires_in_seconds)}</span>
          </p>

          <div className="flex gap-2 pt-2">
            <button
              onClick={handleLogin}
              className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors disabled:opacity-50"
              disabled={loginPending}
            >
              {loginPending ? 'Waiting...' : 'Re-login'}
            </button>
            <button
              onClick={handleLogout}
              className="px-3 py-1.5 bg-red-900/50 hover:bg-red-800/50 text-red-200 text-sm rounded transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${status?.is_expired ? 'bg-yellow-500' : 'bg-gray-500'}`} />
            <span className={status?.is_expired ? 'text-yellow-400' : 'text-gray-400'}>
              {status?.is_expired ? 'Token Expired' : 'Not Connected'}
            </span>
          </div>

          <p className="text-gray-400 text-sm">
            {status?.is_expired
              ? 'Your session has expired. Please login again.'
              : 'Login to use your Claude subscription for loops.'}
          </p>

          {/* Scope selector - only show if in project context */}
          {projectPath && (
            <div className="flex gap-4 text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="scope"
                  checked={selectedScope === 'project'}
                  onChange={() => setSelectedScope('project')}
                  className="accent-blue-500"
                />
                <span className="text-gray-300">This project only</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="scope"
                  checked={selectedScope === 'global'}
                  onChange={() => setSelectedScope('global')}
                  className="accent-blue-500"
                />
                <span className="text-gray-300">Global (all projects)</span>
              </label>
            </div>
          )}

          <button
            onClick={handleLogin}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors disabled:opacity-50"
            disabled={loginPending}
          >
            {loginPending ? 'Waiting for browser...' : 'Login with Claude'}
          </button>
        </div>
      )}
    </div>
  )
}
