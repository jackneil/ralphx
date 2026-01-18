import { useEffect, useState, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import { getProject, listWorkflows, getItemsStats } from '../api'
import type { Workflow } from '../api'
import { useDashboardStore } from '../stores/dashboard'

interface WorkflowProgress {
  id: string
  name: string
  status: string
  current_step: number
  total_steps: number
  progress: number
}

export default function ProjectDashboard() {
  const { slug } = useParams<{ slug: string }>()
  const { selectedProject, setSelectedProject } = useDashboardStore()

  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [itemStats, setItemStats] = useState<{
    total: number
    by_status: Record<string, number>
    by_category: Record<string, number>
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async () => {
    if (!slug) return
    setLoading(true)
    setError(null)

    try {
      const [projectData, workflowsData, statsData] = await Promise.all([
        getProject(slug),
        listWorkflows(slug),
        getItemsStats(slug),
      ])
      setSelectedProject(projectData)
      setWorkflows(workflowsData)
      setItemStats(statsData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard')
    } finally {
      setLoading(false)
    }
  }, [slug, setSelectedProject])

  useEffect(() => {
    loadData()
  }, [loadData])

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading dashboard...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="card bg-red-900/20 border border-red-800">
          <h2 className="text-lg font-semibold text-red-400 mb-2">Error</h2>
          <p className="text-gray-300">{error}</p>
          <Link to="/" className="btn-secondary mt-4 inline-block">
            Back to Dashboard
          </Link>
        </div>
      </div>
    )
  }

  // Calculate workflow progress data
  const workflowProgress: WorkflowProgress[] = workflows.map(w => ({
    id: w.id,
    name: w.name,
    status: w.status,
    current_step: w.current_step,
    total_steps: w.steps.length,
    progress: w.steps.length > 0
      ? Math.round((w.steps.filter(s => s.status === 'completed').length / w.steps.length) * 100)
      : 0,
  }))

  const activeWorkflows = workflowProgress.filter(w => w.status === 'active' || w.status === 'draft' || w.status === 'paused')
  const completedWorkflows = workflowProgress.filter(w => w.status === 'completed')

  // Calculate overall progress
  const totalItems = itemStats?.total || 0
  const completedItems = itemStats?.by_status?.completed || 0
  const inProgressItems = itemStats?.by_status?.in_progress || 0
  const pendingItems = itemStats?.by_status?.pending || 0
  const overallProgress = totalItems > 0 ? Math.round((completedItems / totalItems) * 100) : 0

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
        <span className="text-white">Project Dashboard</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">Project Dashboard</h1>
          <p className="text-gray-400">
            Cross-workflow visibility and progress tracking
          </p>
        </div>
        <Link
          to={`/projects/${slug}`}
          className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
          <span>Workflows View</span>
        </Link>
      </div>

      {/* Overall Progress Card */}
      <div className="card mb-8">
        <h2 className="text-lg font-semibold text-white mb-4">Overall Progress</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-4">
          <div className="text-center">
            <div className="text-3xl font-bold text-primary-400">{workflows.length}</div>
            <div className="text-sm text-gray-400">Total Workflows</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-green-400">{activeWorkflows.length}</div>
            <div className="text-sm text-gray-400">Active</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-blue-400">{completedWorkflows.length}</div>
            <div className="text-sm text-gray-400">Completed</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-yellow-400">{totalItems}</div>
            <div className="text-sm text-gray-400">Total Items</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-white">{overallProgress}%</div>
            <div className="text-sm text-gray-400">Items Complete</div>
          </div>
        </div>
        <div className="w-full bg-gray-700 rounded-full h-3">
          <div
            className="bg-gradient-to-r from-primary-600 to-green-500 h-3 rounded-full transition-all duration-500"
            style={{ width: `${overallProgress}%` }}
          />
        </div>
      </div>

      {/* Item Status Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div className="card">
          <h3 className="text-lg font-semibold text-white mb-4">Item Status</h3>
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Completed</span>
              <div className="flex items-center space-x-2">
                <div className="w-32 bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-green-500 h-2 rounded-full"
                    style={{ width: `${totalItems > 0 ? (completedItems / totalItems) * 100 : 0}%` }}
                  />
                </div>
                <span className="text-green-400 w-12 text-right">{completedItems}</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-300">In Progress</span>
              <div className="flex items-center space-x-2">
                <div className="w-32 bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-yellow-500 h-2 rounded-full"
                    style={{ width: `${totalItems > 0 ? (inProgressItems / totalItems) * 100 : 0}%` }}
                  />
                </div>
                <span className="text-yellow-400 w-12 text-right">{inProgressItems}</span>
              </div>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Pending</span>
              <div className="flex items-center space-x-2">
                <div className="w-32 bg-gray-700 rounded-full h-2">
                  <div
                    className="bg-gray-500 h-2 rounded-full"
                    style={{ width: `${totalItems > 0 ? (pendingItems / totalItems) * 100 : 0}%` }}
                  />
                </div>
                <span className="text-gray-400 w-12 text-right">{pendingItems}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Category Breakdown */}
        <div className="card">
          <h3 className="text-lg font-semibold text-white mb-4">Items by Category</h3>
          {itemStats?.by_category && Object.keys(itemStats.by_category).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(itemStats.by_category)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 6)
                .map(([category, count]) => (
                  <div key={category} className="flex items-center justify-between">
                    <span className="text-gray-300 text-sm font-mono">{category || 'Uncategorized'}</span>
                    <span className="text-primary-400">{count}</span>
                  </div>
                ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No categories yet</p>
          )}
        </div>
      </div>

      {/* Workflow Progress Table */}
      <div className="card">
        <h3 className="text-lg font-semibold text-white mb-4">Workflow Progress</h3>
        {workflows.length === 0 ? (
          <div className="text-center py-8">
            <p className="text-gray-400">No workflows yet</p>
            <Link
              to={`/projects/${slug}`}
              className="text-primary-400 hover:text-primary-300 text-sm mt-2 inline-block"
            >
              Create your first workflow
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="text-left text-sm text-gray-400 border-b border-gray-700">
                  <th className="pb-3 pr-4">Workflow</th>
                  <th className="pb-3 pr-4">Status</th>
                  <th className="pb-3 pr-4">Step</th>
                  <th className="pb-3 pr-4">Progress</th>
                  <th className="pb-3"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {workflowProgress.map((wp) => (
                  <tr key={wp.id} className="hover:bg-gray-800/50">
                    <td className="py-3 pr-4">
                      <Link
                        to={`/projects/${slug}/workflows/${wp.id}`}
                        className="text-white hover:text-primary-400 font-medium"
                      >
                        {wp.name}
                      </Link>
                    </td>
                    <td className="py-3 pr-4">
                      <span
                        className={`px-2 py-1 text-xs rounded ${
                          wp.status === 'completed'
                            ? 'bg-green-900/30 text-green-400'
                            : wp.status === 'active'
                            ? 'bg-blue-900/30 text-blue-400'
                            : 'bg-gray-700 text-gray-400'
                        }`}
                      >
                        {wp.status}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-gray-400 text-sm">
                      {wp.current_step} / {wp.total_steps}
                    </td>
                    <td className="py-3 pr-4">
                      <div className="flex items-center space-x-2">
                        <div className="w-24 bg-gray-700 rounded-full h-2">
                          <div
                            className={`h-2 rounded-full ${
                              wp.status === 'completed' ? 'bg-green-500' : 'bg-primary-500'
                            }`}
                            style={{ width: `${wp.progress}%` }}
                          />
                        </div>
                        <span className="text-sm text-gray-400">{wp.progress}%</span>
                      </div>
                    </td>
                    <td className="py-3 text-right">
                      <Link
                        to={`/projects/${slug}/workflows/${wp.id}`}
                        className="text-primary-400 hover:text-primary-300 text-sm"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
