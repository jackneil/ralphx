import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  Account,
  AccountUsage,
  listAccounts,
  getProjectAccount,
  assignProjectAccount,
  unassignProjectAccount,
  getEffectiveProjectAccount,
} from '../api'

interface ProjectAccountSelectorProps {
  projectId: string
  onAccountChange?: () => void
}

export default function ProjectAccountSelector({
  projectId,
  onAccountChange,
}: ProjectAccountSelectorProps) {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [effectiveAccount, setEffectiveAccount] = useState<Account | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Local state for form controls
  const [selectedAccountId, setSelectedAccountId] = useState<number | 'default'>('default')
  const [allowFallback, setAllowFallback] = useState(true)

  const loadData = async () => {
    setLoading(true)
    try {
      const [accountsData, assignmentData, effectiveData] = await Promise.all([
        listAccounts(),
        getProjectAccount(projectId),
        getEffectiveProjectAccount(projectId),
      ])

      setAccounts(accountsData)
      setEffectiveAccount(effectiveData)

      // Update local state from loaded data
      if (assignmentData) {
        setSelectedAccountId(assignmentData.account_id)
        setAllowFallback(assignmentData.allow_fallback)
      } else {
        setSelectedAccountId('default')
        setAllowFallback(true)
      }

      setError(null)
    } catch (e) {
      setError('Failed to load account settings')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [projectId])

  const handleAccountChange = async (value: string) => {
    const newValue = value === 'default' ? 'default' : parseInt(value, 10)
    setSelectedAccountId(newValue)
    setSaving(true)
    setError(null)

    try {
      if (newValue === 'default') {
        await unassignProjectAccount(projectId)
      } else {
        await assignProjectAccount(projectId, {
          account_id: newValue,
          allow_fallback: allowFallback,
        })
      }
      await loadData()
      onAccountChange?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update account')
      // Revert on error
      loadData()
    } finally {
      setSaving(false)
    }
  }

  const handleFallbackChange = async (checked: boolean) => {
    setAllowFallback(checked)

    // Only save if we have a specific account assigned
    if (selectedAccountId !== 'default') {
      setSaving(true)
      try {
        await assignProjectAccount(projectId, {
          account_id: selectedAccountId as number,
          allow_fallback: checked,
        })
        onAccountChange?.()
      } catch (e) {
        setError('Failed to update fallback setting')
        setAllowFallback(!checked) // Revert
      } finally {
        setSaving(false)
      }
    }
  }

  const getUsageBarColor = (percentage: number): string => {
    if (percentage >= 90) return 'bg-red-500'
    if (percentage >= 71) return 'bg-yellow-500'
    return 'bg-green-500'
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

    if (isToday) return timeStr
    if (isTomorrow) return `tomorrow ${timeStr}`
    return resetDate.toLocaleDateString([], { month: 'short', day: 'numeric' })
  }

  const renderUsageBadge = (usage?: AccountUsage) => {
    if (!usage) return null
    return (
      <span className={`text-xs ${getUsageTextColor(usage.five_hour)}`}>
        5h: {Math.round(usage.five_hour)}% &middot; 7d: {Math.round(usage.seven_day)}%
      </span>
    )
  }

  const getDefaultAccount = () => {
    return accounts.find(a => a.is_default)
  }

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-6 bg-gray-700 rounded w-1/3 mb-4"></div>
        <div className="h-4 bg-gray-700 rounded w-1/2"></div>
      </div>
    )
  }

  // No accounts state
  if (accounts.length === 0) {
    return (
      <div className="card">
        <h2 className="text-lg font-semibold text-white mb-4">Claude Account</h2>
        <div className="text-center py-6">
          <svg
            className="w-10 h-10 text-gray-600 mx-auto mb-3"
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
          <p className="text-gray-400 mb-3">No Claude accounts connected</p>
          <Link
            to="/settings"
            className="text-primary-400 hover:text-primary-300 text-sm"
          >
            Connect an account in Settings &rarr;
          </Link>
        </div>
      </div>
    )
  }

  const defaultAccount = getDefaultAccount()

  return (
    <div className="card">
      <h2 className="text-lg font-semibold text-white mb-4">Claude Account</h2>

      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-red-400 text-sm">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-2 text-red-300 hover:text-red-200"
          >
            &times;
          </button>
        </div>
      )}

      <div className="space-y-4">
        {/* Account selector */}
        <div>
          <label className="block text-sm text-gray-400 mb-2">
            Account for this project
          </label>
          <select
            value={selectedAccountId}
            onChange={(e) => handleAccountChange(e.target.value)}
            disabled={saving}
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white disabled:opacity-50"
          >
            <option value="default">
              Use default account
              {defaultAccount && ` (${defaultAccount.email})`}
            </option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id} disabled={!account.is_active}>
                {account.display_name || account.email}
                {account.is_default && ' ⭐'}
                {!account.is_active && ' (disabled)'}
                {account.usage && ` — 5h: ${Math.round(account.usage.five_hour)}%`}
              </option>
            ))}
          </select>
        </div>

        {/* Show resolved default info when using default */}
        {selectedAccountId === 'default' && defaultAccount && (
          <div className="p-3 bg-gray-700/50 rounded border border-gray-600">
            <p className="text-sm text-gray-400 mb-1">Currently using:</p>
            <div className="flex items-center justify-between">
              <span className="text-white">{defaultAccount.email}</span>
              {defaultAccount.usage && renderUsageBadge(defaultAccount.usage)}
            </div>
          </div>
        )}

        {/* Fallback toggle */}
        <label className="flex items-start space-x-3 cursor-pointer">
          <input
            type="checkbox"
            checked={allowFallback}
            onChange={(e) => handleFallbackChange(e.target.checked)}
            disabled={saving}
            className="mt-1 w-4 h-4 rounded bg-gray-700 border-gray-600 text-primary-500 focus:ring-primary-500 cursor-pointer disabled:opacity-50"
          />
          <div>
            <span className="text-gray-300">Allow fallback when account reaches usage limit</span>
            <p className="text-xs text-gray-500 mt-0.5">
              When rate limited (429), automatically retry with another account that has available capacity
            </p>
          </div>
        </label>

        {/* Effective account display */}
        {effectiveAccount && (
          <div className="pt-4 border-t border-gray-700">
            <p className="text-sm text-gray-400 mb-2">Effective Account</p>
            <div className="p-3 bg-gray-800 rounded border border-gray-700">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-2">
                  <span className="text-white font-medium">{effectiveAccount.email}</span>
                  {effectiveAccount.subscription_type && (
                    <span className="text-xs text-gray-500 capitalize">
                      &middot; {effectiveAccount.subscription_type}
                    </span>
                  )}
                </div>
              </div>

              {/* Usage bars */}
              {effectiveAccount.usage && (
                <div className="flex gap-4 mt-3">
                  {/* 5-hour */}
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-400 text-xs">5h</span>
                      <span className={`text-xs font-medium ${getUsageTextColor(effectiveAccount.usage.five_hour)}`}>
                        {Math.round(effectiveAccount.usage.five_hour)}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-gray-600 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${getUsageBarColor(effectiveAccount.usage.five_hour)}`}
                        style={{ width: `${Math.min(100, effectiveAccount.usage.five_hour)}%` }}
                      />
                    </div>
                    {effectiveAccount.usage.five_hour_resets_at && (
                      <p className="text-gray-500 text-xs mt-0.5">
                        resets {formatResetTime(effectiveAccount.usage.five_hour_resets_at)}
                      </p>
                    )}
                  </div>
                  {/* 7-day */}
                  <div className="flex-1">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-gray-400 text-xs">7d</span>
                      <span className={`text-xs font-medium ${getUsageTextColor(effectiveAccount.usage.seven_day)}`}>
                        {Math.round(effectiveAccount.usage.seven_day)}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-gray-600 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${getUsageBarColor(effectiveAccount.usage.seven_day)}`}
                        style={{ width: `${Math.min(100, effectiveAccount.usage.seven_day)}%` }}
                      />
                    </div>
                    {effectiveAccount.usage.seven_day_resets_at && (
                      <p className="text-gray-500 text-xs mt-0.5">
                        resets {formatResetTime(effectiveAccount.usage.seven_day_resets_at)}
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Link to settings */}
        <div className="pt-2">
          <Link
            to="/settings"
            className="text-sm text-primary-400 hover:text-primary-300"
          >
            Manage accounts in Settings &rarr;
          </Link>
        </div>
      </div>
    </div>
  )
}
