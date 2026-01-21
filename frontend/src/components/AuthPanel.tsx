import { useState, useEffect, useRef } from 'react'
import { getAuthStatus, startLogin, logoutAuth, refreshAuthToken, exportCredentials, getUsage, AuthStatus, CredentialsExport, AuthValidationResult, UsageData } from '../api'

interface AuthPanelProps {
  projectPath?: string  // If provided, shows project-scoped auth
  validationResult?: AuthValidationResult | null  // Result from /validate endpoint
  onLoginSuccess?: () => void  // Called when login completes successfully
}

export default function AuthPanel({ projectPath, validationResult, onLoginSuccess }: AuthPanelProps) {
  const [status, setStatus] = useState<AuthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [loginPending, setLoginPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedScope, setSelectedScope] = useState<'project' | 'global'>(
    projectPath ? 'project' : 'global'
  )
  const [showCredentials, setShowCredentials] = useState(false)
  const [credentialsData, setCredentialsData] = useState<CredentialsExport | null>(null)
  const [loadingCredentials, setLoadingCredentials] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [usage, setUsage] = useState<UsageData | null>(null)
  const [loadingUsage, setLoadingUsage] = useState(false)
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

  // Fetch usage when connected
  useEffect(() => {
    if (status?.connected && !status?.is_expired) {
      setLoadingUsage(true)
      getUsage(projectPath)
        .then(setUsage)
        .catch(() => setUsage(null))
        .finally(() => setLoadingUsage(false))
    }
  }, [status?.connected, status?.is_expired, projectPath])

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
            // Notify parent that login succeeded so it can re-validate
            onLoginSuccess?.()
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

  const handleRefreshToken = async () => {
    setRefreshing(true)
    setError(null)
    try {
      const scope = status?.scope || 'global'
      const result = await refreshAuthToken({ scope, project_path: projectPath })
      if (result.success) {
        await loadStatus() // Reload to get updated expiry
      } else if (result.needs_relogin) {
        setError('Session expired. Please click "Re-login" to authenticate again.')
      } else {
        setError(result.error || 'Failed to refresh token')
      }
    } catch {
      setError('Failed to refresh token')
    } finally {
      setRefreshing(false)
    }
  }

  const handleViewCredentials = async () => {
    setLoadingCredentials(true)
    try {
      const scope = status?.scope || 'global'
      const data = await exportCredentials(scope, projectPath)
      setCredentialsData(data)
      setShowCredentials(true)
    } catch {
      setError('Failed to export credentials')
    } finally {
      setLoadingCredentials(false)
    }
  }

  const handleDownloadCredentials = () => {
    if (!credentialsData?.credentials) return
    const json = JSON.stringify(credentialsData.credentials, null, 2)
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `credentials-${credentialsData.scope || 'global'}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleCopyCredentials = () => {
    if (!credentialsData?.credentials) return
    const json = JSON.stringify(credentialsData.credentials, null, 2)
    navigator.clipboard.writeText(json)
  }

  const formatExpiry = (seconds?: number): string => {
    if (!seconds) return 'Unknown'
    const hours = Math.floor(seconds / 3600)
    const mins = Math.floor((seconds % 3600) / 60)
    if (hours > 0) return `${hours}h ${mins}m`
    return `${mins}m`
  }

  const getUsageTextColor = (utilization: number): string => {
    if (utilization >= 80) return 'text-rose-400'
    if (utilization >= 50) return 'text-amber-400'
    return 'text-emerald-400'
  }

  const getUsageBarColor = (utilization: number): string => {
    if (utilization >= 80) return 'bg-gradient-to-r from-rose-500 to-rose-400'
    if (utilization >= 50) return 'bg-gradient-to-r from-amber-500 to-amber-400'
    return 'bg-gradient-to-r from-emerald-500 to-emerald-400'
  }

  const formatResetTime = (isoString?: string): string => {
    if (!isoString) return ''
    const resetDate = new Date(isoString)
    const now = new Date()
    const isToday = resetDate.toDateString() === now.toDateString()
    const tomorrow = new Date(now)
    tomorrow.setDate(tomorrow.getDate() + 1)
    const isTomorrow = resetDate.toDateString() === tomorrow.toDateString()

    const timeStr = resetDate.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

    if (isToday) return `today at ${timeStr}`
    if (isTomorrow) return `tomorrow at ${timeStr}`
    return resetDate.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ` at ${timeStr}`
  }

  const formatResetLabel = (isoString?: string): string => {
    if (!isoString) return ''
    return `Resets ${formatResetTime(isoString)}`
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

          {/* Connection status - shows validation state if available */}
          {validationResult && !validationResult.valid ? (
            // Token validation failed - show error state
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 bg-yellow-500 rounded-full" />
                <span className="text-yellow-400">Token Invalid</span>
                <span className="text-gray-500 text-sm">
                  ({status.scope === 'project' ? 'Project' : 'Global'})
                </span>
              </div>
              <div className="bg-yellow-500/10 border border-yellow-500 rounded p-3">
                <p className="text-yellow-300/80 text-sm">
                  {validationResult.error || 'Token validation failed'}
                </p>
                <p className="text-gray-400 text-sm mt-1">
                  Please re-login to get fresh credentials.
                </p>
              </div>
            </div>
          ) : (
            // Connected state
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
          )}

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

          {/* Only show plan/tier/expiry info when token is valid */}
          {(!validationResult || validationResult.valid) && (
            <>
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

              {/* API Usage */}
              {(loadingUsage || usage?.success) && (
                <div className="space-y-2">
                  <p className="text-gray-400 text-sm font-medium">API Usage</p>
                  {loadingUsage ? (
                    <div className="text-gray-500">loading...</div>
                  ) : (
                    <div className="flex gap-6">
                      {/* 5-hour */}
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-400 text-sm">5-hour window</span>
                          <span className={`text-sm font-semibold ${getUsageTextColor(usage?.five_hour_utilization || 0)}`}>
                            {Math.round(Math.min(100, usage?.five_hour_utilization || 0))}%
                          </span>
                        </div>
                        <div className="h-3 bg-gray-700/50 rounded-full overflow-hidden shadow-inner">
                          <div
                            className={`h-full rounded-full shadow-sm ${getUsageBarColor(usage?.five_hour_utilization || 0)}`}
                            style={{ width: `${Math.min(100, usage?.five_hour_utilization || 0)}%` }}
                          />
                        </div>
                        {usage?.five_hour_resets_at && (
                          <p className="text-gray-500 text-xs mt-1">Resets {formatResetTime(usage.five_hour_resets_at)}</p>
                        )}
                      </div>
                      {/* 7-day */}
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-400 text-sm">7-day window</span>
                          <span className={`text-sm font-semibold ${getUsageTextColor(usage?.seven_day_utilization || 0)}`}>
                            {Math.round(Math.min(100, usage?.seven_day_utilization || 0))}%
                          </span>
                        </div>
                        <div className="h-3 bg-gray-700/50 rounded-full overflow-hidden shadow-inner">
                          <div
                            className={`h-full rounded-full shadow-sm ${getUsageBarColor(usage?.seven_day_utilization || 0)}`}
                            style={{ width: `${Math.min(100, usage?.seven_day_utilization || 0)}%` }}
                          />
                        </div>
                        {usage?.seven_day_resets_at && (
                          <p className="text-gray-500 text-xs mt-1">Resets {formatResetTime(usage.seven_day_resets_at)}</p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Token expiry and auto-refresh info */}
              <div className="space-y-1">
                <p className="text-gray-400 text-sm">
                  Expires in: <span className="text-white">{formatExpiry(status.expires_in_seconds)}</span>
                </p>
                <p className="text-gray-500 text-xs">
                  Auto-refreshes every 30 min when less than 4 hours remain
                </p>
              </div>
            </>
          )}

          <div className="flex gap-2 pt-2 flex-wrap">
            {/* When token is invalid, make Re-login primary and hide Refresh Token */}
            {validationResult && !validationResult.valid ? (
              <>
                <button
                  onClick={handleLogin}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors disabled:opacity-50"
                  disabled={loginPending}
                >
                  {loginPending ? 'Waiting...' : 'Re-login'}
                </button>
                <button
                  onClick={handleLogout}
                  className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleRefreshToken}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors disabled:opacity-50"
                  disabled={refreshing}
                  title="Get a fresh token now"
                >
                  {refreshing ? 'Refreshing...' : 'Refresh Token'}
                </button>
                <button
                  onClick={handleLogin}
                  className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors disabled:opacity-50"
                  disabled={loginPending}
                >
                  {loginPending ? 'Waiting...' : 'Re-login'}
                </button>
                <button
                  onClick={handleViewCredentials}
                  className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors disabled:opacity-50"
                  disabled={loadingCredentials}
                >
                  {loadingCredentials ? 'Loading...' : 'View Credentials'}
                </button>
                <button
                  onClick={handleLogout}
                  className="px-3 py-1.5 bg-red-900/50 hover:bg-red-800/50 text-red-200 text-sm rounded transition-colors"
                >
                  Logout
                </button>
              </>
            )}
          </div>

          {/* Credentials Panel */}
          {showCredentials && credentialsData && (
            <div className="mt-4 p-4 bg-gray-900 rounded-lg border border-gray-700">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-sm font-medium text-gray-300">
                  Credentials JSON ({credentialsData.scope})
                  {credentialsData.email && (
                    <span className="text-gray-500 ml-2">- {credentialsData.email}</span>
                  )}
                </h4>
                <button
                  onClick={() => setShowCredentials(false)}
                  className="text-gray-500 hover:text-gray-300 text-lg leading-none"
                >
                  &times;
                </button>
              </div>
              {credentialsData.success && credentialsData.credentials ? (
                <>
                  <pre className="text-xs text-gray-400 bg-gray-950 p-3 rounded overflow-x-auto max-h-64 overflow-y-auto">
                    {JSON.stringify(credentialsData.credentials, null, 2)}
                  </pre>
                  <div className="flex gap-2 mt-3">
                    <button
                      onClick={handleCopyCredentials}
                      className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors"
                    >
                      Copy to Clipboard
                    </button>
                    <button
                      onClick={handleDownloadCredentials}
                      className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors"
                    >
                      Download JSON
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Save to ~/.claude/.credentials.json for use with Claude CLI
                  </p>
                </>
              ) : (
                <p className="text-red-400 text-sm">{credentialsData.error || 'No credentials found'}</p>
              )}
            </div>
          )}
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
