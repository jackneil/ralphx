import { useEffect, useState, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import Swal from 'sweetalert2'
import { getProject, listWorkflows, listLoops, getLoopStatus, restoreWorkflow, deleteWorkflow } from '../api'
import type { Workflow } from '../api'
import { useDashboardStore, type Loop } from '../stores/dashboard'
import WorkflowQuickStart from '../components/workflow/WorkflowQuickStart'
import ActiveWorkflowCard from '../components/workflow/ActiveWorkflowCard'

export default function ProjectWorkflowDashboard() {
  const { slug } = useParams<{ slug: string }>()
  const {
    selectedProject,
    setSelectedProject,
    setLoops,
    setLoopsLoading,
  } = useDashboardStore()

  const [error, setError] = useState<string | null>(null)
  const [workflows, setWorkflows] = useState<Workflow[]>([])
  const [archivedWorkflows, setArchivedWorkflows] = useState<Workflow[]>([])
  const [workflowsLoading, setWorkflowsLoading] = useState(true)
  const [hasLegacyLoops, setHasLegacyLoops] = useState(false)
  const [showCreateModal, setShowCreateModal] = useState(false)

  const loadWorkflows = useCallback(async () => {
    if (!slug) return
    setWorkflowsLoading(true)
    try {
      // Load active workflows (non-archived)
      const data = await listWorkflows(slug)
      setWorkflows(data)
      // Load archived workflows separately
      const archived = await listWorkflows(slug, { archived_only: true })
      setArchivedWorkflows(archived)
    } catch {
      setWorkflows([])
      setArchivedWorkflows([])
    } finally {
      setWorkflowsLoading(false)
    }
  }, [slug])

  const loadLoops = useCallback(async () => {
    if (!slug) return
    setLoopsLoading(true)
    try {
      const loopList = await listLoops(slug)
      // Check for legacy loops (loops without workflow_id)
      const legacyLoops = loopList.filter(l => !l.workflow_id)
      setHasLegacyLoops(legacyLoops.length > 0)

      const loopsWithStatus: Loop[] = await Promise.all(
        loopList.map(async (loop) => {
          try {
            const status = await getLoopStatus(slug, loop.name)
            return {
              ...loop,
              is_running: status.is_running,
              current_iteration: status.current_iteration,
              current_mode: status.current_mode,
            }
          } catch {
            return { ...loop, is_running: false }
          }
        })
      )
      setLoops(loopsWithStatus)
    } catch {
      setLoops([])
    } finally {
      setLoopsLoading(false)
    }
  }, [slug, setLoops, setLoopsLoading])

  useEffect(() => {
    if (!slug) return

    setSelectedProject(null)
    setWorkflows([])

    async function loadProject() {
      setError(null)
      try {
        const project = await getProject(slug!)
        setSelectedProject(project)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load project')
      }
    }

    loadProject()
    loadWorkflows()
    loadLoops()
  }, [slug, setSelectedProject, loadWorkflows, loadLoops])

  const handleRestoreWorkflow = async (workflowId: string, workflowName: string) => {
    if (!slug) return

    const result = await Swal.fire({
      title: 'Restore Workflow?',
      text: `Restore "${workflowName}" from the archive?`,
      icon: 'question',
      showCancelButton: true,
      confirmButtonColor: 'var(--color-primary)',
      cancelButtonColor: 'var(--color-slate)',
      confirmButtonText: 'Restore',
      cancelButtonText: 'Cancel',
      background: 'var(--color-surface)',
      color: 'var(--color-text-primary)',
    })

    if (!result.isConfirmed) return

    try {
      await restoreWorkflow(slug, workflowId)
      loadWorkflows()
    } catch (err) {
      Swal.fire({
        title: 'Error',
        text: err instanceof Error ? err.message : 'Failed to restore workflow',
        icon: 'error',
        background: 'var(--color-surface)',
        color: 'var(--color-text-primary)',
      })
    }
  }

  const handlePermanentDelete = async (workflowId: string, workflowName: string) => {
    if (!slug) return

    const result = await Swal.fire({
      title: 'Permanently Delete?',
      html: `<p>This will permanently delete "<strong>${workflowName}</strong>" and all its data.</p><p class="mt-2 text-red-400">This action cannot be undone.</p>`,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: 'var(--color-rose)',
      cancelButtonColor: 'var(--color-slate)',
      confirmButtonText: 'Delete Forever',
      cancelButtonText: 'Cancel',
      background: 'var(--color-surface)',
      color: 'var(--color-text-primary)',
    })

    if (!result.isConfirmed) return

    try {
      await deleteWorkflow(slug, workflowId)
      loadWorkflows()
    } catch (err) {
      Swal.fire({
        title: 'Error',
        text: err instanceof Error ? err.message : 'Failed to delete workflow',
        icon: 'error',
        background: 'var(--color-surface)',
        color: 'var(--color-text-primary)',
      })
    }
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

  if (!selectedProject) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading project...</div>
      </div>
    )
  }

  const activeWorkflows = workflows.filter(w => w.status === 'active' || w.status === 'draft' || w.status === 'paused')
  const completedWorkflows = workflows.filter(w => w.status === 'completed')
  const hasWorkflows = workflows.length > 0
  const showQuickStart = !hasWorkflows && !workflowsLoading

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
          <Link to="/" className="hover:text-white">Dashboard</Link>
          <span>/</span>
          <span className="text-white">{selectedProject.name}</span>
        </div>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-white mb-2">{selectedProject.name}</h1>
            <p className="text-gray-400">{selectedProject.path}</p>
          </div>
          <Link
            to={`/projects/${slug}/settings`}
            className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span>Settings</span>
          </Link>
        </div>
      </div>

      {/* Stats */}
      {selectedProject.stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <div className="card">
            <div className="text-2xl font-bold text-primary-400">
              {workflows.length}
            </div>
            <div className="text-sm text-gray-400">Workflows</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-green-400">
              {activeWorkflows.length}
            </div>
            <div className="text-sm text-gray-400">Active</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-yellow-400">
              {selectedProject.stats.pending_items}
            </div>
            <div className="text-sm text-gray-400">Pending Items</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-blue-400">
              {selectedProject.stats.completed_items}
            </div>
            <div className="text-sm text-gray-400">Completed Items</div>
          </div>
        </div>
      )}

      {/* Quick Start - For new projects without workflows */}
      {showQuickStart && (
        <div className="mb-8 p-6 rounded-xl bg-gradient-to-br from-gray-800 to-gray-900 border border-gray-700">
          <WorkflowQuickStart
            projectSlug={slug!}
            onWorkflowCreated={loadWorkflows}
          />
        </div>
      )}

      {/* Active Workflows */}
      {activeWorkflows.length > 0 && (
        <div className="mb-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold text-white">Active Workflows</h2>
            <button
              onClick={() => setShowCreateModal(true)}
              className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 text-sm"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>New Workflow</span>
            </button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {activeWorkflows.map((workflow) => (
              <ActiveWorkflowCard
                key={workflow.id}
                workflow={workflow}
                projectSlug={slug!}
              />
            ))}
          </div>
        </div>
      )}

      {/* Completed Workflows */}
      {completedWorkflows.length > 0 && (
        <div className="mb-8">
          <details className="group">
            <summary className="flex items-center justify-between cursor-pointer mb-4">
              <h2 className="text-xl font-semibold text-white">
                Completed Workflows
                <span className="ml-2 text-sm font-normal text-gray-400">
                  ({completedWorkflows.length})
                </span>
              </h2>
              <svg className="w-5 h-5 text-gray-400 group-open:rotate-180 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </summary>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {completedWorkflows.map((workflow) => (
                <ActiveWorkflowCard
                  key={workflow.id}
                  workflow={workflow}
                  projectSlug={slug!}
                />
              ))}
            </div>
          </details>
        </div>
      )}

      {/* Archived Workflows */}
      {archivedWorkflows.length > 0 && (
        <div className="mb-8">
          <details className="group">
            <summary className="flex items-center justify-between cursor-pointer mb-4">
              <h2 className="text-xl font-semibold text-gray-400">
                <svg className="w-5 h-5 inline-block mr-2 -mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
                </svg>
                Archived
                <span className="ml-2 text-sm font-normal">
                  ({archivedWorkflows.length})
                </span>
              </h2>
              <svg className="w-5 h-5 text-gray-400 group-open:rotate-180 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </summary>
            <div className="space-y-2">
              {archivedWorkflows.map((workflow) => (
                <div
                  key={workflow.id}
                  className="flex items-center justify-between p-4 rounded-lg bg-gray-800/50 border border-gray-700/50"
                >
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-medium text-gray-400 truncate">{workflow.name}</h3>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Archived {workflow.archived_at ? new Date(workflow.archived_at).toLocaleDateString() : ''}
                    </p>
                  </div>
                  <div className="flex items-center space-x-2 ml-4">
                    <button
                      onClick={() => handleRestoreWorkflow(workflow.id, workflow.name)}
                      className="px-3 py-1.5 text-xs font-medium text-primary-400 bg-primary-900/30 rounded hover:bg-primary-900/50 transition-colors"
                    >
                      Restore
                    </button>
                    <button
                      onClick={() => handlePermanentDelete(workflow.id, workflow.name)}
                      className="px-3 py-1.5 text-xs font-medium text-red-400 bg-red-900/30 rounded hover:bg-red-900/50 transition-colors"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </details>
        </div>
      )}

      {/* Legacy Loops Notice */}
      {hasLegacyLoops && (
        <div className="mb-8 p-4 rounded-lg bg-gray-800 border border-gray-700">
          <div className="flex items-start space-x-3">
            <svg className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <div className="flex-1">
              <h3 className="text-sm font-medium text-white">Legacy Loops Detected</h3>
              <p className="text-sm text-gray-400 mt-1">
                You have standalone loops that aren't part of a workflow.
                These can be migrated to workflows for better organization.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Quick Links */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Link
          to={`/projects/${slug}/dashboard`}
          className="p-4 rounded-lg bg-gray-800 border border-gray-700 hover:border-gray-600 transition-colors group"
        >
          <div className="flex items-center space-x-3">
            <svg className="w-6 h-6 text-gray-400 group-hover:text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            <span className="text-sm text-gray-300 group-hover:text-white">Project Dashboard</span>
          </div>
        </Link>

        <Link
          to={`/projects/${slug}/runs`}
          className="p-4 rounded-lg bg-gray-800 border border-gray-700 hover:border-gray-600 transition-colors group"
        >
          <div className="flex items-center space-x-3">
            <svg className="w-6 h-6 text-gray-400 group-hover:text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm text-gray-300 group-hover:text-white">Run History</span>
          </div>
        </Link>

        <Link
          to={`/projects/${slug}/settings`}
          className="p-4 rounded-lg bg-gray-800 border border-gray-700 hover:border-gray-600 transition-colors group"
        >
          <div className="flex items-center space-x-3">
            <svg className="w-6 h-6 text-gray-400 group-hover:text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
            </svg>
            <span className="text-sm text-gray-300 group-hover:text-white">Shared Resources</span>
          </div>
        </Link>

        <Link
          to={`/projects/${slug}/settings`}
          className="p-4 rounded-lg bg-gray-800 border border-gray-700 hover:border-gray-600 transition-colors group"
        >
          <div className="flex items-center space-x-3">
            <svg className="w-6 h-6 text-gray-400 group-hover:text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            <span className="text-sm text-gray-300 group-hover:text-white">Authentication</span>
          </div>
        </Link>
      </div>

      {/* Create Workflow Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-900 rounded-xl border border-gray-700 p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-semibold text-white">Create New Workflow</h2>
              <button
                onClick={() => setShowCreateModal(false)}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <WorkflowQuickStart
              projectSlug={slug!}
              onWorkflowCreated={() => {
                setShowCreateModal(false)
                loadWorkflows()
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
