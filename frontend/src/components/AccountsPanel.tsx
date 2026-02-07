import { useState, useEffect, useRef } from 'react'
import {
  Account,
  listAccounts,
  addAccount,
  getFlowStatus,
  removeAccount,
  refreshAllAccountsUsage,
  reorderAccounts,
  updateAccount,
  validateAccount,
} from '../api'

interface AccountsPanelProps {
  onAccountChange?: () => void
}

export default function AccountsPanel({ onAccountChange }: AccountsPanelProps) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [addingAccount, setAddingAccount] = useState(false)
  const [actionInProgress, setActionInProgress] = useState<number | null>(null)
  const [validatingAccounts, setValidatingAccounts] = useState<Set<number>>(new Set())
  const [refreshingAll, setRefreshingAll] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null)
  const [draggedId, setDraggedId] = useState<number | null>(null)
  const [dragOverId, setDragOverId] = useState<number | null>(null)
  const [now, setNow] = useState(Date.now())
  const pollRef = useRef<number | null>(null)
  const timeoutRef = useRef<number | null>(null)
  const confirmTimeoutRef = useRef<number | null>(null)
  const validatedAccountsRef = useRef<Set<number>>(new Set())  // Track which accounts we've validated this session
  const mountedRef = useRef(true)  // Track if component is mounted

  const loadAccounts = async (refreshUsageIfStale = false) => {
    try {
      const data = await listAccounts(true)
      setAccounts(data)
      setError(null)

      // Auto-refresh usage for accounts that have no usage data or stale data (>5 min)
      if (refreshUsageIfStale) {
        const now = Date.now() / 1000
        const staleThreshold = 5 * 60 // 5 minutes
        const needsRefresh = data.some(
          (acc: Account) => !acc.usage || !acc.usage_cached_at || (now - acc.usage_cached_at > staleThreshold)
        )
        if (needsRefresh) {
          // Refresh all in background, then reload
          refreshAllAccountsUsage().then(() => loadAccounts(false)).catch(() => {})
        }
      }
    } catch (e) {
      setError('Failed to load accounts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    mountedRef.current = true
    loadAccounts(true) // Refresh usage on initial load if stale
    // Refresh accounts list periodically + tick the "last updated" timer
    const interval = setInterval(() => { loadAccounts(false); setNow(Date.now()) }, 30000)
    return () => {
      mountedRef.current = false
      clearInterval(interval)
      if (pollRef.current) clearInterval(pollRef.current)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current)
    }
  }, [])

  // Validate accounts that haven't been validated recently (5 minutes)
  useEffect(() => {
    if (loading || accounts.length === 0) return

    const fiveMinAgo = Date.now() / 1000 - 300

    // Find accounts that need validation
    const accountsToValidate = accounts.filter((account) => {
      // Skip if we already validated this account in this session
      if (validatedAccountsRef.current.has(account.id)) return false
      // Skip if recently validated (within 5 minutes) by backend
      if (account.last_validated_at && account.last_validated_at > fiveMinAgo) return false
      // Skip if already known expired (no point validating)
      if (account.is_expired) return false
      // Skip if disabled
      if (!account.is_active) return false
      return true
    })

    if (accountsToValidate.length === 0) return

    // Validate each account
    accountsToValidate.forEach(async (account) => {
      // Mark as validated for this session immediately to prevent duplicate calls
      validatedAccountsRef.current.add(account.id)

      // Check if component still mounted before state updates
      if (!mountedRef.current) return

      setValidatingAccounts(prev => new Set(prev).add(account.id))
      try {
        await validateAccount(account.id)
      } catch {
        // Validation errors are stored on backend, we'll fetch them below
      } finally {
        // Check mounted before updating state
        if (mountedRef.current) {
          setValidatingAccounts(prev => {
            const next = new Set(prev)
            next.delete(account.id)
            return next
          })
          // Always refresh to get updated validation status (success or failure)
          await loadAccounts(false)
        }
      }
    })
  }, [loading, accounts])  // Re-run when accounts change to catch newly added accounts

  const handleAddAccount = async (expectedEmail?: string) => {
    setAddingAccount(true)
    setError(null)

    try {
      const startResult = await addAccount(expectedEmail)
      if (!startResult.success || !startResult.flow_id) {
        setError(startResult.error || 'Failed to start login')
        setAddingAccount(false)
        return
      }

      const flowId = startResult.flow_id

      // Poll for OAuth flow completion
      pollRef.current = window.setInterval(async () => {
        try {
          const flowStatus = await getFlowStatus(flowId)

          if (flowStatus.status === 'completed' && flowStatus.result) {
            // Clear polling
            if (pollRef.current) clearInterval(pollRef.current)
            if (timeoutRef.current) clearTimeout(timeoutRef.current)

            const result = flowStatus.result

            if (!result.success) {
              setError(result.error || 'OAuth flow failed')
              setAddingAccount(false)
              return
            }

            // Handle email mismatch warning
            if (result.email_mismatch && result.message) {
              setError(`\u26A0\uFE0F ${result.message}`)
            }

            // Refresh accounts list to show the new/updated account
            await loadAccounts()
            setAddingAccount(false)
            onAccountChange?.()
          } else if (flowStatus.status === 'error') {
            if (pollRef.current) clearInterval(pollRef.current)
            if (timeoutRef.current) clearTimeout(timeoutRef.current)
            setError(flowStatus.error || 'OAuth flow failed')
            setAddingAccount(false)
          } else if (flowStatus.status === 'not_found') {
            // Flow expired or was cleaned up - stop polling
            if (pollRef.current) clearInterval(pollRef.current)
            if (timeoutRef.current) clearTimeout(timeoutRef.current)
            setError('OAuth flow expired. Please try again.')
            setAddingAccount(false)
          }
          // status === 'pending' - keep polling
        } catch {
          // Ignore polling errors, keep trying
        }
      }, 1000)

      // Timeout after 2 minutes
      timeoutRef.current = window.setTimeout(() => {
        if (pollRef.current) clearInterval(pollRef.current)
        setAddingAccount(false)
        setError('Account linking timed out. Please try again.')
      }, 120000)
    } catch (e) {
      setError('Failed to start account linking')
      setAddingAccount(false)
    }
  }

  const handleRequestDelete = (account: Account) => {
    const hasOtherAccounts = accounts.filter(a => a.id !== account.id).length > 0

    if (sortedAccounts[0]?.id === account.id && hasOtherAccounts) {
      setError('Cannot remove the primary account while other accounts exist. Drag another account to the top first.')
      return
    }

    // Show inline confirmation
    setConfirmDeleteId(account.id)

    // Auto-cancel after 5 seconds
    if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current)
    confirmTimeoutRef.current = window.setTimeout(() => {
      setConfirmDeleteId(null)
    }, 5000)
  }

  const handleConfirmDelete = async (account: Account) => {
    if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current)
    setConfirmDeleteId(null)
    setActionInProgress(account.id)
    try {
      await removeAccount(account.id)
      await loadAccounts()
      onAccountChange?.()
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to remove account'
      setError(msg)
    } finally {
      setActionInProgress(null)
    }
  }

  const handleCancelDelete = () => {
    if (confirmTimeoutRef.current) clearTimeout(confirmTimeoutRef.current)
    setConfirmDeleteId(null)
  }

  const handleRefreshAllUsage = async () => {
    setRefreshingAll(true)
    try {
      await refreshAllAccountsUsage()
      await loadAccounts(false)
      setNow(Date.now())
    } catch {
      setError('Failed to refresh usage')
    } finally {
      setRefreshingAll(false)
    }
  }

  const handleToggleActive = async (account: Account) => {
    setActionInProgress(account.id)
    try {
      await updateAccount(account.id, { is_active: !account.is_active })
      await loadAccounts()
      onAccountChange?.()
    } catch {
      setError('Failed to update account')
    } finally {
      setActionInProgress(null)
    }
  }

  const getUsageBarColor = (percentage: number): string => {
    if (percentage >= 90) return 'bg-red-500'
    if (percentage >= 71) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  const getElapsedPct = (resetsAt: string | undefined, windowHours: number): number | null => {
    if (!resetsAt) return null
    const reset = new Date(resetsAt).getTime()
    const now = Date.now()
    const durationMs = windowHours * 60 * 60 * 1000
    const start = reset - durationMs
    if (now < start || now > reset) return null
    return Math.min(100, Math.max(0, ((now - start) / durationMs) * 100))
  }

  const getUsageTextColor = (percentage: number): string => {
    if (percentage >= 90) return 'text-red-400'
    if (percentage >= 71) return 'text-yellow-400'
    return 'text-green-400'
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

    if (isToday) return `today ${timeStr}`
    if (isTomorrow) return `tomorrow ${timeStr}`
    return `${resetDate.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })} ${timeStr}`
  }

  const getUsageCacheAge = (cachedAt?: number, currentTime: number = now): string => {
    if (!cachedAt) return 'never'
    const ageMs = currentTime - cachedAt * 1000
    const minutes = Math.floor(ageMs / 60000)
    if (minutes < 1) return 'just now'
    if (minutes < 60) return `${minutes}m ago`
    const hours = Math.round((minutes / 60) * 10) / 10
    return `${hours}h ago`
  }

  // Sort accounts by priority for display
  const sortedAccounts = [...accounts].sort((a, b) => (a.priority ?? 0) - (b.priority ?? 0))

  // Most recent usage cache timestamp across all accounts
  const latestCacheAge = (() => {
    const timestamps = accounts.map(a => a.usage_cached_at).filter(Boolean) as number[]
    if (timestamps.length === 0) return null
    return Math.max(...timestamps)
  })()

  const getPriorityLabel = (index: number): string => {
    if (index === 0) return 'Primary'
    return `Fallback ${index}`
  }

  const handleDragStart = (e: React.DragEvent, accountId: number) => {
    setDraggedId(accountId)
    e.dataTransfer.effectAllowed = 'move'
  }

  const handleDragOver = (e: React.DragEvent, accountId: number) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    if (accountId !== draggedId) {
      setDragOverId(accountId)
    }
  }

  const handleDragLeave = () => {
    setDragOverId(null)
  }

  const handleDrop = async (e: React.DragEvent, targetId: number) => {
    e.preventDefault()
    setDragOverId(null)
    if (draggedId === null || draggedId === targetId) {
      setDraggedId(null)
      return
    }

    // Reorder: move dragged item to target position
    const newOrder = sortedAccounts.map(a => a.id)
    const fromIndex = newOrder.indexOf(draggedId)
    const toIndex = newOrder.indexOf(targetId)
    newOrder.splice(fromIndex, 1)
    newOrder.splice(toIndex, 0, draggedId)

    setDraggedId(null)

    // Optimistic update
    const updatedAccounts = accounts.map(acc => ({
      ...acc,
      priority: newOrder.indexOf(acc.id),
      is_default: newOrder.indexOf(acc.id) === 0,
    }))
    setAccounts(updatedAccounts)

    // Persist to backend
    try {
      await reorderAccounts(newOrder)
    } catch {
      // Revert on error
      await loadAccounts()
    }
  }

  const handleDragEnd = () => {
    setDraggedId(null)
    setDragOverId(null)
  }

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="h-4 bg-gray-700 rounded w-1/2"></div>
      </div>
    )
  }

  // Empty state
  if (accounts.length === 0) {
    return (
      <div className="card">
        <div className="text-center py-8">
          <svg
            className="w-12 h-12 text-gray-600 mx-auto mb-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M18 9v3m0 0v3m0-3h3m-3 0h-3m-2-5a4 4 0 11-8 0 4 4 0 018 0zM3 20a6 6 0 0112 0v1H3v-1z"
            />
          </svg>
          <h3 className="text-lg font-medium text-white mb-2">No Claude accounts connected</h3>
          <p className="text-gray-400 mb-4">
            Connect your Claude account to start running workflows automatically.
          </p>
          <button
            onClick={() => handleAddAccount()}
            disabled={addingAccount}
            className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 disabled:opacity-50"
          >
            {addingAccount ? 'Waiting for browser...' : '+ Connect Account'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white">Claude Accounts</h2>
          {latestCacheAge && (
            <p className="text-xs text-gray-500 mt-0.5">Last updated: {getUsageCacheAge(latestCacheAge)}</p>
          )}
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={handleRefreshAllUsage}
            disabled={refreshingAll}
            className="flex items-center space-x-1.5 px-3 py-1.5 text-gray-400 hover:text-white hover:bg-gray-600/50 text-sm rounded transition-colors disabled:opacity-50"
            title="Refresh usage for all accounts"
          >
            <svg className={`w-3.5 h-3.5 ${refreshingAll ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span>{refreshingAll ? 'Refreshing...' : 'Refresh Usage'}</span>
          </button>
          <button
            onClick={() => handleAddAccount()}
            disabled={addingAccount}
            className="flex items-center space-x-1.5 px-3 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-500 transition-colors disabled:opacity-50"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>{addingAccount ? 'Waiting...' : 'Add Account'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className={`mb-4 p-3 rounded text-sm ${
          error.startsWith('\u26A0\uFE0F')
            ? 'bg-yellow-900/30 border border-yellow-800 text-yellow-400'
            : 'bg-red-900/30 border border-red-800 text-red-400'
        }`}>
          {error}
          <button
            onClick={() => setError(null)}
            className={`ml-2 ${
              error.startsWith('\u26A0\uFE0F')
                ? 'text-yellow-300 hover:text-yellow-200'
                : 'text-red-300 hover:text-red-200'
            }`}
          >
            &times;
          </button>
        </div>
      )}

      <div className="space-y-3">
        {sortedAccounts.map((account, index) => (
          <div
            key={account.id}
            draggable={sortedAccounts.length > 1}
            onDragStart={(e) => handleDragStart(e, account.id)}
            onDragOver={(e) => handleDragOver(e, account.id)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, account.id)}
            onDragEnd={handleDragEnd}
            className={`p-4 rounded-lg border transition-all ${
              draggedId === account.id
                ? 'opacity-50'
                : dragOverId === account.id
                ? 'border-primary-500 bg-primary-900/20'
                : account.is_expired
                ? 'bg-yellow-900/10 border-yellow-800/50'
                : account.validation_status === 'invalid'
                ? 'bg-orange-900/10 border-orange-800/50'
                : account.is_active
                ? 'bg-gray-700/50 border-gray-600'
                : 'bg-gray-800/50 border-gray-700 opacity-60'
            }`}
          >
            {/* Header row */}
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-3">
                {/* Drag handle — only show when there are multiple accounts */}
                {sortedAccounts.length > 1 && (
                  <div className="cursor-grab active:cursor-grabbing text-gray-500 hover:text-gray-300 select-none text-lg leading-none" title="Drag to reorder">
                    &#x2807;
                  </div>
                )}
                <div
                  className={`w-2.5 h-2.5 rounded-full ${
                    validatingAccounts.has(account.id)
                      ? 'bg-blue-500 animate-pulse'  // Pulsing blue = checking
                      : account.is_expired || account.validation_status === 'invalid'
                      ? 'bg-yellow-500'  // Yellow = needs attention
                      : account.is_active
                      ? 'bg-green-500'   // Green = valid
                      : 'bg-gray-500'    // Gray = disabled
                  }`}
                />
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-white font-medium text-base">
                      {account.email}
                    </span>
                    <span className={`px-1.5 py-0.5 text-xs rounded font-medium ${
                      index === 0
                        ? 'bg-green-600/20 text-green-400'
                        : 'bg-gray-600/30 text-gray-400'
                    }`}>
                      {getPriorityLabel(index)}
                    </span>
                    {validatingAccounts.has(account.id) && (
                      <span className="px-1.5 py-0.5 bg-blue-600/30 text-blue-400 text-xs rounded font-medium">
                        CHECKING...
                      </span>
                    )}
                    {account.validation_status === 'invalid' && !account.is_expired && !validatingAccounts.has(account.id) && (
                      <span className="px-1.5 py-0.5 bg-orange-600/30 text-orange-400 text-xs rounded font-medium">
                        TOKEN INVALID
                      </span>
                    )}
                    {account.is_expired && (
                      <span className="px-1.5 py-0.5 bg-yellow-600/30 text-yellow-400 text-xs rounded font-medium">
                        EXPIRED
                      </span>
                    )}
                    {!account.is_active && (
                      <span className="px-1.5 py-0.5 bg-gray-600/30 text-gray-400 text-xs rounded font-medium">
                        DISABLED
                      </span>
                    )}
                  </div>
                  <div className="text-gray-400 text-sm mt-0.5 flex items-center gap-2">
                    {account.subscription_type ? (
                      <span className="capitalize font-medium text-gray-300">
                        {account.subscription_type}
                        {account.rate_limit_tier?.includes('20x') && ' 20x'}
                      </span>
                    ) : account.usage ? (
                      <span className="text-gray-400">Claude</span>
                    ) : (
                      <span className="text-gray-500">Not verified</span>
                    )}
                    <span className="text-gray-600">&middot;</span>
                    <span>{account.projects_using} project{account.projects_using !== 1 ? 's' : ''}</span>
                    {account.display_name && (
                      <>
                        <span className="text-gray-600">&middot;</span>
                        <span className="text-gray-500">{account.display_name}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center space-x-1">
                {confirmDeleteId === account.id ? (
                  /* Inline delete confirmation */
                  <div className="flex items-center space-x-2">
                    <span className="text-red-400 text-xs">Remove?</span>
                    <button
                      onClick={() => handleConfirmDelete(account)}
                      className="px-2 py-0.5 text-xs text-white bg-red-600 hover:bg-red-500 rounded"
                    >
                      Yes
                    </button>
                    <button
                      onClick={handleCancelDelete}
                      className="px-2 py-0.5 text-xs text-gray-400 hover:text-white hover:bg-gray-600 rounded"
                    >
                      Cancel
                    </button>
                  </div>
                ) : account.is_expired || (account.validation_status === 'invalid' && !validatingAccounts.has(account.id)) ? (
                  <>
                    <button
                      onClick={() => handleAddAccount(account.email)}
                      disabled={addingAccount}
                      className={`px-2 py-1 text-sm text-white rounded disabled:opacity-50 ${
                        account.is_expired
                          ? 'bg-yellow-600 hover:bg-yellow-500'
                          : 'bg-orange-600 hover:bg-orange-500'
                      }`}
                    >
                      Re-auth
                    </button>
                    <button
                      onClick={() => handleRequestDelete(account)}
                      disabled={actionInProgress === account.id}
                      className="p-1 text-gray-400 hover:text-red-400 hover:bg-red-900/30 rounded"
                      title="Remove account"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={() => handleAddAccount(account.email)}
                      disabled={addingAccount}
                      className="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-600 rounded"
                      title="Re-authenticate this account"
                    >
                      Re-auth
                    </button>
                    <button
                      onClick={() => handleToggleActive(account)}
                      disabled={actionInProgress === account.id}
                      className="px-2 py-1 text-xs text-gray-400 hover:text-white hover:bg-gray-600 rounded"
                      title={account.is_active ? 'Disable account' : 'Enable account'}
                    >
                      {account.is_active ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      onClick={() => handleRequestDelete(account)}
                      disabled={actionInProgress === account.id}
                      className="p-1 text-gray-400 hover:text-red-400 hover:bg-red-900/30 rounded"
                      title="Remove account"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Usage section - always show for non-expired, valid accounts */}
            {!account.is_expired && account.validation_status !== 'invalid' && (
              <div className="mt-3 pt-3 border-t border-gray-600/50">
                {account.usage ? (
                  <>
                    <div className="flex gap-6">
                      {/* 5-hour usage */}
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-400 text-xs font-medium">5-hour limit</span>
                          <span className={`text-sm font-semibold ${getUsageTextColor(account.usage.five_hour)}`}>
                            {Math.round(account.usage.five_hour)}% used
                          </span>
                        </div>
                        <div className="h-2 bg-gray-600 rounded-full overflow-hidden relative">
                          <div
                            className={`h-full rounded-full transition-all ${getUsageBarColor(account.usage.five_hour)}`}
                            style={{ width: `${Math.min(100, account.usage.five_hour)}%` }}
                          />
                          {(() => {
                            const pct = getElapsedPct(account.usage.five_hour_resets_at, 5)
                            return pct != null ? <div className="absolute top-0 bottom-0 w-0.5 bg-white/70 pointer-events-none" style={{ left: `${pct}%` }} /> : null
                          })()}
                        </div>
                        <p className="text-gray-500 text-xs mt-1">
                          {account.usage.five_hour_resets_at && new Date(account.usage.five_hour_resets_at) > new Date()
                          ? `Resets ${formatResetTime(account.usage.five_hour_resets_at)}`
                          : 'No active window'}
                        </p>
                      </div>
                      {/* 7-day usage */}
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-gray-400 text-xs font-medium">7-day limit</span>
                          <span className={`text-sm font-semibold ${getUsageTextColor(account.usage.seven_day)}`}>
                            {Math.round(account.usage.seven_day)}% used
                          </span>
                        </div>
                        <div className="h-2 bg-gray-600 rounded-full overflow-hidden relative">
                          <div
                            className={`h-full rounded-full transition-all ${getUsageBarColor(account.usage.seven_day)}`}
                            style={{ width: `${Math.min(100, account.usage.seven_day)}%` }}
                          />
                          {(() => {
                            const pct = getElapsedPct(account.usage.seven_day_resets_at, 168)
                            return pct != null ? <div className="absolute top-0 bottom-0 w-0.5 bg-white/70 pointer-events-none" style={{ left: `${pct}%` }} /> : null
                          })()}
                        </div>
                        <p className="text-gray-500 text-xs mt-1">
                          {account.usage.seven_day_resets_at && new Date(account.usage.seven_day_resets_at) > new Date()
                          ? `Resets ${formatResetTime(account.usage.seven_day_resets_at)}`
                          : 'No active window'}
                        </p>
                      </div>
                    </div>
                  </>
                ) : (
                  <span className="text-gray-500 text-xs">Usage data not available</span>
                )}
              </div>
            )}

            {/* Invalid token state */}
            {account.validation_status === 'invalid' && !account.is_expired && (
              <div className="mt-3 pt-3 border-t border-gray-600/50">
                <p className="text-orange-400 text-sm">
                  Token validation failed. Please re-authenticate to continue using this account.
                </p>
                {account.last_error && (
                  <p className="text-gray-500 text-xs mt-1">
                    {account.last_error}
                  </p>
                )}
              </div>
            )}

            {/* Error state (only show if not invalid - invalid has its own section) */}
            {account.last_error && account.validation_status !== 'invalid' && (
              <div className="mt-3 pt-3 border-t border-gray-600/50">
                <p className="text-red-400 text-xs">
                  {account.last_error}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Info box */}
      <div className="mt-4 p-3 bg-gray-800/50 border border-gray-700 rounded">
        <div className="flex items-start space-x-2">
          <svg
            className="w-4 h-4 text-gray-500 mt-0.5 flex-shrink-0"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p className="text-gray-400 text-xs">
            The top account is used by default for all projects. Drag to reorder priority.
            When rate limited, RalphX automatically retries with the next account.
          </p>
        </div>
      </div>
    </div>
  )
}
