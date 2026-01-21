import { useEffect, useState, useCallback } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import {
  getProject,
  getAuthStatus,
  getUsage,
  startLogin,
  logoutAuth,
  listProjectResources,
  createProjectResource,
  updateProjectResource,
  deleteProjectResource,
  getProjectSettings,
  updateProjectSettings,
  ProjectResource,
  ProjectSettings as ProjectSettingsType,
  AuthStatus,
  UsageData,
} from '../api'
import { useDashboardStore } from '../stores/dashboard'

type SettingsTab = 'auth' | 'resources' | 'defaults'

export default function ProjectSettings() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const { selectedProject, setSelectedProject } = useDashboardStore()

  const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null)
  const [usage, setUsage] = useState<UsageData | null>(null)
  const [resources, setResources] = useState<ProjectResource[]>([])
  const [settings, setSettings] = useState<ProjectSettingsType | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [loginLoading, setLoginLoading] = useState(false)
  const [savingSettings, setSavingSettings] = useState(false)

  // Active tab - read from URL parameter or default to 'auth'
  const tabParam = searchParams.get('tab') as SettingsTab | null
  const validTabs: SettingsTab[] = ['auth', 'resources', 'defaults']
  const initialTab = tabParam && validTabs.includes(tabParam) ? tabParam : 'auth'
  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab)

  // Update URL when tab changes
  const handleTabChange = (tab: SettingsTab) => {
    setActiveTab(tab)
    setSearchParams({ tab })
  }

  // Add resource modal
  const [showAddModal, setShowAddModal] = useState(false)
  const [newResource, setNewResource] = useState({
    name: '',
    resource_type: 'guardrail',
    content: '',
    description: '',
    auto_inherit: true,
  })
  const [adding, setAdding] = useState(false)

  // Edit modal
  const [editResource, setEditResource] = useState<ProjectResource | null>(null)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)

  const loadData = useCallback(async () => {
    if (!slug) return
    setLoading(true)
    setError(null)

    try {
      const [projectData, authData, resourcesData, settingsData] = await Promise.all([
        getProject(slug),
        getAuthStatus(),
        listProjectResources(slug),
        getProjectSettings(slug),
      ])
      setSelectedProject(projectData)
      setAuthStatus(authData)
      setResources(resourcesData)
      setSettings(settingsData)
      // Fetch usage if connected
      if (authData?.connected && !authData?.is_expired) {
        getUsage().then(setUsage).catch(() => setUsage(null))
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings')
    } finally {
      setLoading(false)
    }
  }, [slug, setSelectedProject])

  useEffect(() => {
    loadData()
  }, [loadData])

  const handleLogin = async () => {
    setLoginLoading(true)
    setError(null)
    try {
      await startLogin({ scope: 'global' })
      // Refresh auth status after a short delay to allow OAuth flow
      setTimeout(() => {
        loadData()
        setLoginLoading(false)
      }, 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start login')
      setLoginLoading(false)
    }
  }

  const handleLogout = async () => {
    if (!confirm('Are you sure you want to disconnect your authentication?')) return

    try {
      await logoutAuth({ scope: 'global' })
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to logout')
    }
  }

  const handleAddResource = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!slug || !newResource.name.trim() || !newResource.content.trim()) return

    setAdding(true)
    try {
      await createProjectResource(slug, {
        name: newResource.name.trim(),
        resource_type: newResource.resource_type,
        content: newResource.content.trim(),
        description: newResource.description.trim() || undefined,
        auto_inherit: newResource.auto_inherit,
      })
      setNewResource({
        name: '',
        resource_type: 'guardrail',
        content: '',
        description: '',
        auto_inherit: true,
      })
      setShowAddModal(false)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add resource')
    } finally {
      setAdding(false)
    }
  }

  const handleSaveEdit = async () => {
    if (!slug || !editResource) return

    setSaving(true)
    try {
      await updateProjectResource(slug, editResource.id, {
        content: editContent,
      })
      setEditResource(null)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save resource')
    } finally {
      setSaving(false)
    }
  }

  const handleToggleAutoInherit = async (resource: ProjectResource) => {
    if (!slug) return

    try {
      await updateProjectResource(slug, resource.id, {
        auto_inherit: !resource.auto_inherit,
      })
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update resource')
    }
  }

  const handleDeleteResource = async (resource: ProjectResource) => {
    if (!slug) return
    if (!confirm(`Delete "${resource.name}"? This cannot be undone.`)) return

    try {
      await deleteProjectResource(slug, resource.id)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete resource')
    }
  }

  const handleSettingChange = async (
    key: 'auto_inherit_guardrails' | 'require_design_doc' | 'architecture_first_mode',
    value: boolean
  ) => {
    if (!slug || !settings) return

    // Optimistic update
    setSettings({ ...settings, [key]: value })
    setSavingSettings(true)

    try {
      const updated = await updateProjectSettings(slug, { [key]: value })
      setSettings(updated)
    } catch (err) {
      // Revert on error
      setSettings({ ...settings, [key]: !value })
      setError(err instanceof Error ? err.message : 'Failed to save setting')
    } finally {
      setSavingSettings(false)
    }
  }

  const getResourceTypeLabel = (type: string) => {
    switch (type) {
      case 'design_doc': return 'Design Document'
      case 'guardrail': return 'Guardrail'
      case 'prompt': return 'Prompt Template'
      default: return type
    }
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

  const tabs: { key: SettingsTab; label: string }[] = [
    { key: 'auth', label: 'Authentication' },
    { key: 'resources', label: 'Shared Resources' },
    { key: 'defaults', label: 'Defaults' },
  ]

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
        <Link to="/" className="hover:text-white">Dashboard</Link>
        <span>/</span>
        <Link to={`/projects/${slug}`} className="hover:text-white">
          {selectedProject?.name || slug}
        </Link>
        <span>/</span>
        <span className="text-white">Settings</span>
      </div>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-white mb-1">Project Settings</h1>
        <p className="text-gray-400">
          Configure authentication and shared resources for all workflows.
        </p>
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-red-400">
          {error}
        </div>
      )}

      {/* Tabs */}
      <div className="flex space-x-1 mb-6 border-b border-gray-700">
        {tabs.map(tab => (
          <button
            key={tab.key}
            onClick={() => handleTabChange(tab.key)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              activeTab === tab.key
                ? 'border-primary-500 text-white'
                : 'border-transparent text-gray-400 hover:text-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Authentication Tab */}
      {activeTab === 'auth' && (
        <div className="space-y-6">
          <div className="card">
            <h2 className="text-lg font-semibold text-white mb-4">Claude Authentication</h2>

            {authStatus?.connected ? (
              <div className="space-y-4">
                <div className="flex items-center space-x-3">
                  <div className="w-3 h-3 rounded-full bg-green-500" />
                  <span className="text-green-400">Connected</span>
                </div>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-400">Email:</span>
                    <span className="text-white ml-2">{authStatus.email || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Subscription:</span>
                    <span className="text-white ml-2">{authStatus.subscription_type || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Scope:</span>
                    <span className="text-white ml-2">{authStatus.scope || 'global'}</span>
                  </div>
                  <div>
                    <span className="text-gray-400">Rate Limit:</span>
                    <span className="text-white ml-2">{authStatus.rate_limit_tier || 'N/A'}</span>
                  </div>
                  {usage?.success && (
                    <div className="col-span-2 mt-2 pt-3 border-t border-gray-700">
                      <p className="text-gray-400 text-sm font-medium mb-2">API Usage</p>
                      <div className="flex gap-6">
                        {/* 5-hour */}
                        <div className="flex-1">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-gray-400 text-sm">5-hour</span>
                            <span className={`text-sm font-semibold ${getUsageTextColor(usage.five_hour_utilization || 0)}`}>
                              {Math.round(Math.min(100, usage.five_hour_utilization || 0))}%
                            </span>
                          </div>
                          <div className="h-3 bg-gray-700/50 rounded-full overflow-hidden shadow-inner">
                            <div
                              className={`h-full rounded-full shadow-sm ${getUsageBarColor(usage.five_hour_utilization || 0)}`}
                              style={{ width: `${Math.min(100, usage.five_hour_utilization || 0)}%` }}
                            />
                          </div>
                          {usage.five_hour_resets_at && (
                            <p className="text-gray-500 text-xs mt-1">Resets {formatResetTime(usage.five_hour_resets_at)}</p>
                          )}
                        </div>
                        {/* 7-day */}
                        <div className="flex-1">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-gray-400 text-sm">7-day</span>
                            <span className={`text-sm font-semibold ${getUsageTextColor(usage.seven_day_utilization || 0)}`}>
                              {Math.round(Math.min(100, usage.seven_day_utilization || 0))}%
                            </span>
                          </div>
                          <div className="h-3 bg-gray-700/50 rounded-full overflow-hidden shadow-inner">
                            <div
                              className={`h-full rounded-full shadow-sm ${getUsageBarColor(usage.seven_day_utilization || 0)}`}
                              style={{ width: `${Math.min(100, usage.seven_day_utilization || 0)}%` }}
                            />
                          </div>
                          {usage.seven_day_resets_at && (
                            <p className="text-gray-500 text-xs mt-1">Resets {formatResetTime(usage.seven_day_resets_at)}</p>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
                <button
                  onClick={handleLogout}
                  className="px-4 py-2 text-sm rounded bg-red-900/30 text-red-400 hover:bg-red-900/50"
                >
                  Disconnect
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center space-x-3">
                  <div className="w-3 h-3 rounded-full bg-gray-500" />
                  <span className="text-gray-400">Not connected</span>
                </div>
                <p className="text-sm text-gray-500">
                  Connect your Claude account to enable AI-powered features.
                </p>
                <button
                  onClick={handleLogin}
                  disabled={loginLoading}
                  className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50"
                >
                  {loginLoading ? 'Connecting...' : 'Connect Claude Account'}
                </button>
              </div>
            )}
          </div>

          <div className="p-4 bg-gray-800/50 border border-gray-700 rounded">
            <div className="flex items-start space-x-3">
              <svg className="w-5 h-5 text-yellow-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="text-sm text-gray-400">
                <p className="font-medium text-gray-300 mb-1">About Authentication</p>
                <p>
                  Authentication is shared across all workflows in this project.
                  Claude uses these credentials to interact with the Claude API.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Shared Resources Tab */}
      {activeTab === 'resources' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white">Shared Resource Library</h2>
              <p className="text-sm text-gray-400">
                Resources here can be imported into any workflow.
              </p>
            </div>
            <button
              onClick={() => setShowAddModal(true)}
              className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>Add Shared Resource</span>
            </button>
          </div>

          {resources.length === 0 ? (
            <div className="card text-center py-8">
              <p className="text-gray-400">No shared resources yet</p>
              <p className="text-sm text-gray-500 mt-2">
                Add resources to the library to share across workflows.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {resources.map(resource => (
                <div key={resource.id} className="card flex items-start justify-between">
                  <div className="flex items-start space-x-4">
                    <div className="p-2 rounded bg-primary-500/20 text-primary-400">
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="text-lg font-medium text-white">{resource.name}</h3>
                      <div className="flex items-center space-x-4 text-sm text-gray-400 mt-1">
                        <span>{getResourceTypeLabel(resource.resource_type)}</span>
                      </div>
                      {resource.description && (
                        <p className="text-sm text-gray-500 mt-2">
                          {resource.description}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() => handleToggleAutoInherit(resource)}
                      className={`px-3 py-1 text-sm rounded ${
                        resource.auto_inherit
                          ? 'bg-primary-600/20 text-primary-400'
                          : 'bg-gray-700 text-gray-500'
                      }`}
                    >
                      {resource.auto_inherit ? 'Auto-inherit' : 'Manual'}
                    </button>
                    <button
                      onClick={() => {
                        setEditResource(resource)
                        setEditContent(resource.content || '')
                      }}
                      className="px-3 py-1 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
                    >
                      View
                    </button>
                    <button
                      onClick={() => handleDeleteResource(resource)}
                      className="px-3 py-1 text-sm rounded bg-red-900/30 text-red-400 hover:bg-red-900/50"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="p-4 bg-gray-800/50 border border-gray-700 rounded">
            <div className="flex items-start space-x-3">
              <svg className="w-5 h-5 text-yellow-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="text-sm text-gray-400">
                <p className="font-medium text-gray-300 mb-1">About Auto-inherit</p>
                <p>
                  Resources marked as "auto-inherit" are automatically added to new workflows.
                  This is useful for company-wide guardrails or standards.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Defaults Tab */}
      {activeTab === 'defaults' && (
        <div className="space-y-6">
          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Default Settings for New Workflows</h2>
              {savingSettings && (
                <span className="text-sm text-gray-400">Saving...</span>
              )}
            </div>
            <p className="text-sm text-gray-400 mb-4">
              These settings are applied to new workflows by default.
            </p>

            <div className="space-y-4">
              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings?.auto_inherit_guardrails ?? true}
                  onChange={(e) => handleSettingChange('auto_inherit_guardrails', e.target.checked)}
                  disabled={savingSettings}
                  className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-primary-500 focus:ring-primary-500 cursor-pointer disabled:opacity-50"
                />
                <div>
                  <span className="text-gray-300">Auto-inherit shared guardrails</span>
                  <p className="text-xs text-gray-500">New workflows automatically receive guardrails marked as auto-inherit</p>
                </div>
              </label>
              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings?.require_design_doc ?? false}
                  onChange={(e) => handleSettingChange('require_design_doc', e.target.checked)}
                  disabled={savingSettings}
                  className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-primary-500 focus:ring-primary-500 cursor-pointer disabled:opacity-50"
                />
                <div>
                  <span className="text-gray-300">Require design document before implementation</span>
                  <p className="text-xs text-gray-500">Blocks autonomous steps until a design document is attached</p>
                </div>
              </label>
              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={settings?.architecture_first_mode ?? false}
                  onChange={(e) => handleSettingChange('architecture_first_mode', e.target.checked)}
                  disabled={savingSettings}
                  className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-primary-500 focus:ring-primary-500 cursor-pointer disabled:opacity-50"
                />
                <div>
                  <span className="text-gray-300">Enable architecture-first mode</span>
                  <p className="text-xs text-gray-500">Prioritizes planning and design steps in new workflows</p>
                </div>
              </label>
            </div>
          </div>

          <div className="p-4 bg-gray-800/50 border border-gray-700 rounded">
            <div className="flex items-start space-x-3">
              <svg className="w-5 h-5 text-green-400 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div className="text-sm text-gray-400">
                <p className="font-medium text-gray-300 mb-1">Settings Auto-Save</p>
                <p>
                  Changes are saved automatically when you toggle a setting.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Add Resource Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-bold text-white mb-4">Add Shared Resource</h2>
            <form onSubmit={handleAddResource} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Resource Type
                </label>
                <select
                  value={newResource.resource_type}
                  onChange={(e) => setNewResource({ ...newResource, resource_type: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                >
                  <option value="guardrail">Guardrail</option>
                  <option value="prompt">Prompt Template</option>
                  <option value="design_doc">Design Template</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Name
                </label>
                <input
                  type="text"
                  value={newResource.name}
                  onChange={(e) => setNewResource({ ...newResource, name: e.target.value })}
                  placeholder="e.g., HIPAA Compliance Guidelines"
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Description (optional)
                </label>
                <input
                  type="text"
                  value={newResource.description}
                  onChange={(e) => setNewResource({ ...newResource, description: e.target.value })}
                  placeholder="Brief description..."
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Content
                </label>
                <textarea
                  value={newResource.content}
                  onChange={(e) => setNewResource({ ...newResource, content: e.target.value })}
                  placeholder="Resource content..."
                  rows={10}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 font-mono text-sm"
                />
              </div>
              <label className="flex items-center space-x-3">
                <input
                  type="checkbox"
                  checked={newResource.auto_inherit}
                  onChange={(e) => setNewResource({ ...newResource, auto_inherit: e.target.checked })}
                  className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-primary-500 focus:ring-primary-500"
                />
                <span className="text-gray-300">Auto-add to new workflows</span>
              </label>
              <div className="flex justify-end space-x-3">
                <button
                  type="button"
                  onClick={() => setShowAddModal(false)}
                  className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={adding || !newResource.name.trim() || !newResource.content.trim()}
                  className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50"
                >
                  {adding ? 'Adding...' : 'Add Resource'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {editResource && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">{editResource.name}</h2>
              <span className="text-sm bg-gray-700 text-gray-400 px-2 py-1 rounded">
                {getResourceTypeLabel(editResource.resource_type)}
              </span>
            </div>
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              rows={20}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white font-mono text-sm"
            />
            <div className="flex justify-end space-x-3 mt-4">
              <button
                onClick={() => setEditResource(null)}
                className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={saving}
                className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50"
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
