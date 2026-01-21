import { useEffect, useState, useCallback } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import Swal from 'sweetalert2'
import {
  getWorkflow,
  runSpecificStep,
  stopWorkflow,
  advanceWorkflowStep,
} from '../api'
import type { Workflow } from '../api'
import PlanningChat from '../components/planning/PlanningChat'
import SessionHistory from '../components/SessionHistory'
import WorkflowItemsTab from '../components/workflow/WorkflowItemsTab'

type TabType = 'overview' | 'logs' | 'items'

export default function StepDetail() {
  const { slug, workflowId, stepNumber } = useParams<{
    slug: string
    workflowId: string
    stepNumber: string
  }>()
  const navigate = useNavigate()

  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<TabType>('overview')

  const stepNum = stepNumber ? parseInt(stepNumber, 10) : null

  const loadWorkflow = useCallback(async () => {
    if (!slug || !workflowId) return
    try {
      const data = await getWorkflow(slug, workflowId)
      setWorkflow(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflow')
    } finally {
      setLoading(false)
    }
  }, [slug, workflowId])

  useEffect(() => {
    loadWorkflow()
  }, [loadWorkflow])

  // Poll for updates when step is running
  useEffect(() => {
    if (!workflow) return

    const step = workflow.steps?.find(s => s.step_number === stepNum)
    if (!step?.has_active_run) return

    const interval = setInterval(loadWorkflow, 2000)
    return () => clearInterval(interval)
  }, [workflow, stepNum, loadWorkflow])

  // Get current step
  const steps = workflow?.steps || []
  const step = steps.find(s => s.step_number === stepNum)

  // Validate step exists
  useEffect(() => {
    if (!loading && workflow && !step) {
      // Step not found - redirect to workflow dashboard
      navigate(`/projects/${slug}/workflows/${workflowId}`, { replace: true })
    }
  }, [loading, workflow, step, navigate, slug, workflowId])

  // Validate step is not archived
  useEffect(() => {
    if (step?.archived_at) {
      navigate(`/projects/${slug}/workflows/${workflowId}`, { replace: true })
    }
  }, [step, navigate, slug, workflowId])

  const handleRunStep = async () => {
    if (!slug || !workflowId || !stepNum) return

    const stepName = step?.name || `Step ${stepNum}`

    const result = await Swal.fire({
      title: 'Run Ralph Loop?',
      text: `Start executing "${stepName}"?`,
      icon: 'question',
      showCancelButton: true,
      confirmButtonColor: 'var(--color-primary)',
      cancelButtonColor: 'var(--color-slate)',
      confirmButtonText: 'Run Ralph Loop',
      cancelButtonText: 'Cancel',
      background: 'var(--color-surface)',
      color: 'var(--color-text-primary)',
    })

    if (!result.isConfirmed) return

    setActionLoading(true)
    try {
      const updated = await runSpecificStep(slug, workflowId, stepNum)
      setWorkflow(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run step')
    } finally {
      setActionLoading(false)
    }
  }

  const handleStopStep = async () => {
    if (!slug || !workflowId) return

    const result = await Swal.fire({
      title: 'Stop Step?',
      text: 'This will stop the current execution. You can resume later.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: 'var(--color-rose)',
      cancelButtonColor: 'var(--color-slate)',
      confirmButtonText: 'Stop',
      cancelButtonText: 'Cancel',
      background: 'var(--color-surface)',
      color: 'var(--color-text-primary)',
    })

    if (!result.isConfirmed) return

    setActionLoading(true)
    try {
      const updated = await stopWorkflow(slug, workflowId)
      setWorkflow(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop step')
    } finally {
      setActionLoading(false)
    }
  }

  const handleAdvance = async (skipCurrent: boolean = false) => {
    if (!slug || !workflowId) return
    setActionLoading(true)
    try {
      const updated = await advanceWorkflowStep(slug, workflowId, { skip_current: skipCurrent })
      setWorkflow(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to advance workflow')
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 w-64 bg-[var(--color-elevated)] rounded" />
          <div className="h-8 w-96 bg-[var(--color-elevated)] rounded" />
          <div className="h-64 bg-[var(--color-elevated)] rounded" />
        </div>
      </div>
    )
  }

  if (error && !workflow) {
    return (
      <div className="p-6">
        <div className="card bg-red-900/20 border border-red-800">
          <h2 className="text-lg font-semibold text-red-400 mb-2">Error</h2>
          <p className="text-gray-300">{error}</p>
          <Link to={`/projects/${slug}/workflows/${workflowId}`} className="btn-secondary mt-4 inline-block">
            Back to Workflow
          </Link>
        </div>
      </div>
    )
  }

  if (!workflow || !step) {
    return null // Will redirect via useEffect
  }

  const isInteractiveStep = step.step_type === 'interactive'
  const isAutonomousStep = step.step_type === 'autonomous'
  const isRunning = step.has_active_run === true
  const isCurrentActiveStep = step.step_number === workflow.current_step && step.status === 'active'

  // Calculate items count for this step
  const itemsCount = step.items_generated || 0

  // Status badge color
  const getStepStatusColor = () => {
    if (isRunning) return 'bg-green-600'
    switch (step.status) {
      case 'completed': return 'bg-blue-600'
      case 'active': return 'bg-amber-600'
      case 'skipped': return 'bg-gray-600'
      default: return 'bg-gray-600'
    }
  }

  const getStepStatusLabel = () => {
    if (isRunning) return 'Running'
    switch (step.status) {
      case 'completed': return 'Completed'
      case 'active': return 'Active'
      case 'skipped': return 'Skipped'
      default: return 'Pending'
    }
  }

  return (
    <div className="p-6">
      {/* Breadcrumbs + Back */}
      <div className="mb-6">
        <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
          <Link
            to={`/projects/${slug}/workflows/${workflowId}`}
            className="flex items-center gap-1 hover:text-white transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Workflow
          </Link>
          <span>/</span>
          <Link to="/" className="hover:text-white">Dashboard</Link>
          <span>/</span>
          <Link to={`/projects/${slug}`} className="hover:text-white">{slug}</Link>
          <span>/</span>
          <Link to={`/projects/${slug}/workflows/${workflowId}`} className="hover:text-white">
            {workflow.name}
          </Link>
          <span>/</span>
          <span className="text-white">Step {step.step_number}</span>
        </div>

        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <h1 className="text-2xl font-bold text-white">
              Step {step.step_number}: {step.name}
            </h1>
            <span className={`px-3 py-1 rounded-full text-sm font-medium text-white ${getStepStatusColor()}`}>
              {getStepStatusLabel()}
            </span>
            <span className="px-2 py-1 text-xs font-medium bg-[var(--color-elevated)] text-[var(--color-text-muted)] rounded">
              {isInteractiveStep ? 'Chat' : 'Auto'}
            </span>
          </div>

          <div className="flex items-center space-x-3">
            {/* Run button - show when step is not running */}
            {!isRunning && workflow.status !== 'completed' && (
              <button
                onClick={handleRunStep}
                disabled={actionLoading}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-500 transition-colors disabled:opacity-50"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Run</span>
              </button>
            )}

            {/* Stop button - show when step is running */}
            {isRunning && (
              <button
                onClick={handleStopStep}
                disabled={actionLoading}
                className="flex items-center space-x-2 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-500 transition-colors disabled:opacity-50"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
                </svg>
                <span>Stop</span>
              </button>
            )}

            {/* Edit button */}
            <button
              onClick={() => navigate(`/projects/${slug}/workflows/${workflowId}/edit`)}
              className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              <span>Edit</span>
            </button>
          </div>
        </div>

        {/* Step description */}
        {step.config?.description && (
          <p className="mt-2 text-gray-400">{step.config.description}</p>
        )}
      </div>

      {/* Error Banner */}
      {error && workflow && (
        <div className="mb-6 p-4 rounded-lg bg-red-900/20 border border-red-800">
          <div className="flex items-center justify-between">
            <p className="text-red-400 text-sm">{error}</p>
            <button
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-300"
              aria-label="Dismiss error"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Tab Bar */}
      <div className="flex border-b border-[var(--color-border)] mb-6">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-3 text-sm font-medium transition-colors relative
            ${activeTab === 'overview'
              ? 'text-cyan-400'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'}`}
        >
          Overview
          {activeTab === 'overview' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-500" />
          )}
        </button>
        {isAutonomousStep && (
          <button
            onClick={() => setActiveTab('logs')}
            className={`px-4 py-3 text-sm font-medium transition-colors relative
              ${activeTab === 'logs'
                ? 'text-cyan-400'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'}`}
          >
            Logs
            {isRunning && (
              <span className="ml-2 w-2 h-2 bg-green-500 rounded-full inline-block animate-pulse" />
            )}
            {activeTab === 'logs' && (
              <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-500" />
            )}
          </button>
        )}
        <button
          onClick={() => setActiveTab('items')}
          className={`px-4 py-3 text-sm font-medium transition-colors relative flex items-center gap-2
            ${activeTab === 'items'
              ? 'text-cyan-400'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'}`}
        >
          Items
          {itemsCount > 0 && (
            <span className="px-1.5 py-0.5 text-xs rounded-full bg-cyan-500/20 text-cyan-400">
              {itemsCount}
            </span>
          )}
          {activeTab === 'items' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-500" />
          )}
        </button>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Step Info Card */}
          <div className="card">
            <h2 className="text-lg font-semibold text-white mb-4">Step Configuration</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <div className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide mb-1">Type</div>
                <div className="text-[var(--color-text-primary)]">
                  {isInteractiveStep ? 'Interactive (Chat)' : 'Autonomous (Auto)'}
                </div>
              </div>
              <div>
                <div className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide mb-1">Status</div>
                <div className="text-[var(--color-text-primary)]">{getStepStatusLabel()}</div>
              </div>
              <div>
                <div className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide mb-1">Iterations</div>
                <div className="text-[var(--color-text-primary)]">{step.iterations_completed || 0}</div>
              </div>
              <div>
                <div className="text-xs text-[var(--color-text-muted)] uppercase tracking-wide mb-1">Items Generated</div>
                <div className="text-[var(--color-text-primary)]">{itemsCount}</div>
              </div>
            </div>

            {/* Skip button for skippable steps */}
            {isCurrentActiveStep && step.config?.skippable && (
              <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
                <button
                  onClick={() => handleAdvance(true)}
                  disabled={actionLoading}
                  className="text-sm text-gray-400 hover:text-white transition-colors"
                >
                  Skip this step
                </button>
              </div>
            )}
          </div>

          {/* Interactive Step: Show Chat if active */}
          {isInteractiveStep && isCurrentActiveStep && (
            <div className="card">
              <h2 className="text-lg font-semibold text-white mb-4">Planning Chat</h2>
              <PlanningChat
                projectSlug={slug!}
                workflowId={workflowId!}
                onComplete={loadWorkflow}
              />
            </div>
          )}

          {/* Interactive Step: Not active */}
          {isInteractiveStep && !isCurrentActiveStep && (
            <div className="card text-center py-8">
              {step.status === 'pending' && (
                <>
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-800 flex items-center justify-center">
                    <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <p className="text-gray-400">This step hasn't started yet.</p>
                </>
              )}
              {step.status === 'completed' && (
                <>
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green-900/30 flex items-center justify-center">
                    <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <p className="text-green-400">Step completed!</p>
                </>
              )}
            </div>
          )}

          {/* Autonomous Step: Show preview of logs */}
          {isAutonomousStep && step.loop_name && (
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-lg font-semibold text-white">Session Logs</h2>
                <button
                  onClick={() => setActiveTab('logs')}
                  className="text-sm text-cyan-400 hover:text-cyan-300 transition-colors"
                >
                  View Full Logs
                </button>
              </div>
              <SessionHistory
                projectSlug={slug!}
                loopName={step.loop_name}
                enabled={true}
              />
            </div>
          )}

          {/* Autonomous Step: No loop configured yet */}
          {isAutonomousStep && !step.loop_name && step.status === 'pending' && (
            <div className="card text-center py-8">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-gray-800 flex items-center justify-center">
                <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
              </div>
              <p className="text-gray-400">This autonomous step hasn't been configured yet.</p>
              <p className="text-gray-500 text-sm mt-2">Run the step to initialize it.</p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'logs' && isAutonomousStep && (
        <div className="card">
          {step.loop_name ? (
            <SessionHistory
              projectSlug={slug!}
              loopName={step.loop_name}
              enabled={true}
            />
          ) : (
            <div className="text-center py-12 text-gray-400">
              <div className="w-12 h-12 mx-auto mb-3 rounded-full bg-gray-800 flex items-center justify-center">
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p>No executions yet</p>
              <p className="text-sm text-gray-500 mt-1">Run the step to see logs here</p>
            </div>
          )}
        </div>
      )}

      {activeTab === 'items' && (
        <div className="card">
          <WorkflowItemsTab
            projectSlug={slug!}
            workflowId={workflowId!}
            sourceStepId={step.id}
            steps={workflow?.steps || []}
            onImported={() => loadWorkflow()}
          />
        </div>
      )}
    </div>
  )
}
