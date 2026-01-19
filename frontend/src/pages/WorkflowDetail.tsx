import { useEffect, useState, useCallback } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import Swal from 'sweetalert2'
import {
  getWorkflow,
  startWorkflow,
  stopWorkflow,
  advanceWorkflowStep,
  archiveWorkflow,
  runSpecificStep,
  listWorkflowResources,
  updateWorkflowResource,
} from '../api'
import type { Workflow, ImportJsonlResponse, WorkflowResource } from '../api'
import WorkflowTimeline from '../components/workflow/WorkflowTimeline'
import WorkflowItemsTab from '../components/workflow/WorkflowItemsTab'
import PlanningChat from '../components/planning/PlanningChat'
import ImportJsonlModal from '../components/workflow/ImportJsonlModal'
import SessionHistory from '../components/SessionHistory'

export default function WorkflowDetail() {
  const { slug, workflowId } = useParams<{ slug: string; workflowId: string }>()
  const navigate = useNavigate()

  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [resources, setResources] = useState<WorkflowResource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [importResult, setImportResult] = useState<ImportJsonlResponse | null>(null)
  const [selectedStepNumber, setSelectedStepNumber] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<'steps' | 'items'>('steps')
  const [itemsSourceStepId, setItemsSourceStepId] = useState<number | undefined>(undefined)

  const loadWorkflow = useCallback(async () => {
    if (!slug || !workflowId) return
    try {
      const [data, resourcesData] = await Promise.all([
        getWorkflow(slug, workflowId),
        listWorkflowResources(slug, workflowId),
      ])
      setWorkflow(data)
      setResources(resourcesData)
      setError(null) // Clear any previous errors on successful load
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflow')
    } finally {
      setLoading(false)
    }
  }, [slug, workflowId])

  useEffect(() => {
    loadWorkflow()
  }, [loadWorkflow])

  // Poll for updates when workflow is active (autonomous step running)
  useEffect(() => {
    if (!workflow || workflow.status === 'completed' || workflow.status === 'draft') return

    // Poll every 2s when active for responsive UI updates
    const interval = setInterval(loadWorkflow, 2000)
    return () => clearInterval(interval)
  }, [workflow, loadWorkflow])

  const handleStartClick = async () => {
    const result = await Swal.fire({
      title: 'Start Workflow?',
      text: 'This will begin executing the workflow from the current step.',
      icon: 'question',
      showCancelButton: true,
      confirmButtonColor: 'var(--color-primary)',
      cancelButtonColor: 'var(--color-slate)',
      confirmButtonText: 'Start',
      cancelButtonText: 'Cancel',
      background: 'var(--color-surface)',
      color: 'var(--color-text-primary)',
    })

    if (result.isConfirmed) {
      await handleConfirmStart()
    }
  }

  const handleConfirmStart = async () => {
    if (!slug || !workflowId) return
    setActionLoading(true)
    try {
      const updated = await startWorkflow(slug, workflowId)
      setWorkflow(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start workflow')
    } finally {
      setActionLoading(false)
    }
  }

  const handleStop = async () => {
    if (!slug || !workflowId) return

    const result = await Swal.fire({
      title: 'Stop Workflow?',
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
      setError(err instanceof Error ? err.message : 'Failed to stop workflow')
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

  const handleArchive = async () => {
    if (!slug || !workflowId) return

    const result = await Swal.fire({
      title: 'Archive Workflow?',
      text: 'This workflow will be moved to the archive. You can restore it later from project settings.',
      icon: 'info',
      showCancelButton: true,
      confirmButtonColor: 'var(--color-primary)',
      cancelButtonColor: 'var(--color-slate)',
      confirmButtonText: 'Archive',
      cancelButtonText: 'Cancel',
      background: 'var(--color-surface)',
      color: 'var(--color-text-primary)',
    })

    if (!result.isConfirmed) return

    setActionLoading(true)
    try {
      await archiveWorkflow(slug, workflowId)
      navigate(`/projects/${slug}/workflows`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to archive workflow')
      setActionLoading(false)
    }
  }

  const handleRunStep = async (stepNumber: number) => {
    if (!slug || !workflowId) return

    const stepName = (workflow?.steps || []).find(s => s.step_number === stepNumber)?.name || `Step ${stepNumber}`

    const result = await Swal.fire({
      title: 'Run Step?',
      text: `Start executing "${stepName}"?`,
      icon: 'question',
      showCancelButton: true,
      confirmButtonColor: 'var(--color-primary)',
      cancelButtonColor: 'var(--color-slate)',
      confirmButtonText: 'Run',
      cancelButtonText: 'Cancel',
      background: 'var(--color-surface)',
      color: 'var(--color-text-primary)',
    })

    if (!result.isConfirmed) return

    setActionLoading(true)
    try {
      const updated = await runSpecificStep(slug, workflowId, stepNumber)
      setWorkflow(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run step')
    } finally {
      setActionLoading(false)
    }
  }

  const handleViewItems = (stepId: number) => {
    setItemsSourceStepId(stepId)
    setActiveTab('items')
  }

  const handleResourceUpdate = async (resourceId: number, content: string, expectedUpdatedAt: string) => {
    if (!slug || !workflowId) return

    await updateWorkflowResource(slug, workflowId, resourceId, {
      content,
      expected_updated_at: expectedUpdatedAt,
    })

    // Reload to get updated resources
    await loadWorkflow()
  }

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading workflow...</div>
      </div>
    )
  }

  // Only show full error screen if we have no workflow data
  // (i.e., initial load failed, not a transient polling error)
  if (error && !workflow) {
    return (
      <div className="p-6">
        <div className="card bg-red-900/20 border border-red-800">
          <h2 className="text-lg font-semibold text-red-400 mb-2">Error</h2>
          <p className="text-gray-300">{error}</p>
          <Link to={`/projects/${slug}/workflows`} className="btn-secondary mt-4 inline-block">
            Back to Workflows
          </Link>
        </div>
      </div>
    )
  }

  if (!workflow) {
    return (
      <div className="p-6">
        <div className="card">
          <p className="text-gray-400">Workflow not found</p>
        </div>
      </div>
    )
  }

  // Defensive: ensure steps array exists (TypeScript says required, but runtime could differ)
  const steps = workflow.steps || []

  const currentStep = steps.find(s => s.step_number === workflow.current_step)

  // Selected step for viewing logs (defaults to current step)
  const effectiveSelectedStep = selectedStepNumber ?? workflow.current_step
  const selectedStep = steps.find(s => s.step_number === effectiveSelectedStep) || currentStep

  const isInteractiveStep = selectedStep?.step_type === 'interactive'
  const isAutonomousStep = selectedStep?.step_type === 'autonomous'

  // Check if anything is ACTUALLY running (not just workflow status)
  // This is the source of truth - if any step has an active run, something is running
  const isActuallyRunning = steps.some(s => s.has_active_run === true)

  // Map workflow.status to display status
  const getDisplayStatus = () => {
    if (workflow.status === 'active') {
      return isActuallyRunning ? 'running' : 'idle'
    }
    return workflow.status
  }

  const displayStatus = getDisplayStatus()

  // Determine what button to show based on actual execution state
  const canRun = workflow.status !== 'completed' && !isActuallyRunning
  const canStop = isActuallyRunning

  const statusColors: Record<string, string> = {
    draft: 'bg-gray-600',
    running: 'bg-green-600',
    idle: 'bg-amber-600',
    active: 'bg-green-600', // Keep for fallback
    paused: 'bg-yellow-600',
    completed: 'bg-blue-600',
    failed: 'bg-red-600',
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
          <Link to="/" className="hover:text-white">Dashboard</Link>
          <span>/</span>
          <Link to={`/projects/${slug}`} className="hover:text-white">{slug}</Link>
          <span>/</span>
          <Link to={`/projects/${slug}/workflows`} className="hover:text-white">Workflows</Link>
          <span>/</span>
          <span className="text-white">{workflow.name}</span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <h1 className="text-3xl font-bold text-white">{workflow.name}</h1>
            <span className={`px-3 py-1 rounded-full text-sm font-medium text-white ${statusColors[displayStatus]}`}>
              {displayStatus.charAt(0).toUpperCase() + displayStatus.slice(1)}
            </span>
          </div>

          <div className="flex items-center space-x-3">
            {/* Run button - show when nothing is running and workflow isn't completed */}
            {canRun && (
              <button
                onClick={handleStartClick}
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

            {/* Stop button - show only when something is actually running */}
            {canStop && (
              <button
                onClick={handleStop}
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

            {/* Import Button - only show in draft/paused state */}
            {(workflow.status === 'draft' || workflow.status === 'paused') && (
              <button
                onClick={() => setShowImport(true)}
                className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
                title="Import work items from JSONL file"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M9 19l3-3m0 0l3 3m-3-3v12" />
                </svg>
                <span>Import</span>
              </button>
            )}

            <button
              onClick={() => navigate(`/projects/${slug}/workflows/${workflowId}/edit`)}
              className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              <span>Edit</span>
            </button>

            <button
              onClick={handleArchive}
              className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
              title="Archive workflow"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
              </svg>
              <span>Archive</span>
            </button>
          </div>
        </div>
      </div>

      {/* Error Banner (for transient errors when we still have data) */}
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
          onClick={() => setActiveTab('steps')}
          className={`px-4 py-3 text-sm font-medium transition-colors relative
            ${activeTab === 'steps'
              ? 'text-cyan-400'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'}`}
        >
          Steps
          {activeTab === 'steps' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-500" />
          )}
        </button>
        <button
          onClick={() => { setActiveTab('items'); setItemsSourceStepId(undefined); }}
          className={`px-4 py-3 text-sm font-medium transition-colors relative flex items-center gap-2
            ${activeTab === 'items'
              ? 'text-cyan-400'
              : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]'}`}
        >
          Items
          {steps.reduce((sum, s) => sum + (s.items_generated || 0), 0) > 0 && (
            <span className="px-1.5 py-0.5 text-xs rounded-full bg-cyan-500/20 text-cyan-400">
              {steps.reduce((sum, s) => sum + (s.items_generated || 0), 0)}
            </span>
          )}
          {activeTab === 'items' && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-500" />
          )}
        </button>
      </div>

      {/* Items Tab Content */}
      {activeTab === 'items' && (
        <div className="card">
          <WorkflowItemsTab
            projectSlug={slug!}
            workflowId={workflowId!}
            sourceStepId={itemsSourceStepId}
          />
        </div>
      )}

      {/* Steps Tab Content */}
      {activeTab === 'steps' && (
        <>
          {/* Resource Summary + Step Navigation */}
          <div className="mb-8">
            <WorkflowTimeline
              steps={steps}
              currentStep={workflow.current_step}
              selectedStep={effectiveSelectedStep}
              resources={resources}
              projectSlug={slug}
              workflowId={workflowId}
              onStepSelect={(stepNum) => setSelectedStepNumber(stepNum)}
              onRunStep={handleRunStep}
              onItemsClick={handleViewItems}
              onResourceUpdate={handleResourceUpdate}
              isRunning={actionLoading}
            />
          </div>

          {/* Current Step Content - Full Width */}
          <div className="space-y-6">
          {selectedStep && (
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-white">
                  Step {selectedStep.step_number}: {selectedStep.name}
                </h2>
                {selectedStep.step_number === workflow.current_step && selectedStep.config?.skippable && selectedStep.status === 'active' && (
                  <button
                    onClick={() => handleAdvance(true)}
                    disabled={actionLoading}
                    className="text-sm text-gray-400 hover:text-white"
                  >
                    Skip this step
                  </button>
                )}
              </div>

              {selectedStep.config?.description && (
                <p className="text-gray-400 mb-6">{selectedStep.config.description}</p>
              )}

              {/* Interactive Step: Show Chat (only for current active step) */}
              {isInteractiveStep && selectedStep.step_number === workflow.current_step && selectedStep.status === 'active' && (
                <PlanningChat
                  projectSlug={slug!}
                  workflowId={workflowId!}
                  onComplete={loadWorkflow}
                />
              )}

              {/* Autonomous Step: Always show session logs if loop_name exists */}
              {isAutonomousStep && selectedStep.loop_name && (
                <SessionHistory
                  projectSlug={slug!}
                  loopName={selectedStep.loop_name}
                  enabled={true}
                />
              )}

              {/* Autonomous Step: No loop configured yet */}
              {isAutonomousStep && !selectedStep.loop_name && selectedStep.status === 'pending' && (
                <div className="text-center py-8 text-gray-400">
                  <p>This autonomous step hasn't been configured yet.</p>
                </div>
              )}

              {/* Pending Interactive Step */}
              {isInteractiveStep && selectedStep.status === 'pending' && (
                <div className="text-center py-8 text-gray-400">
                  <p>This step hasn't started yet.</p>
                  {workflow.status === 'draft' && selectedStep.step_number === 1 && (
                    <button
                      onClick={handleStartClick}
                      className="mt-4 px-6 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 transition-colors"
                    >
                      Start Workflow
                    </button>
                  )}
                </div>
              )}

              {/* Completed Interactive Step */}
              {isInteractiveStep && selectedStep.status === 'completed' && (
                <div className="text-center py-8">
                  <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-green-900/30 flex items-center justify-center">
                    <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                  <p className="text-green-400">Step completed!</p>
                </div>
              )}
            </div>
          )}

          {/* Workflow Completed */}
          {workflow.status === 'completed' && (
            <div className="card text-center py-8">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-blue-900/30 flex items-center justify-center">
                <svg className="w-8 h-8 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-white mb-2">Workflow Complete!</h3>
              <p className="text-gray-400">All steps have been completed successfully.</p>
            </div>
          )}
          </div>
        </>
      )}

      {/* Import JSONL Modal */}
      {showImport && (
        <ImportJsonlModal
          projectSlug={slug!}
          workflowId={workflowId!}
          steps={steps}
          onClose={() => setShowImport(false)}
          onImported={(result) => {
            setImportResult(result)
            setShowImport(false)
            loadWorkflow() // Refresh to show new items
          }}
        />
      )}

      {/* Import Success Banner */}
      {importResult && (
        <div className="fixed bottom-6 right-6 p-4 rounded-lg bg-green-900/90 border border-green-700 shadow-lg max-w-sm">
          <div className="flex items-start justify-between">
            <div>
              <h4 className="text-green-400 font-medium">Import Complete</h4>
              <p className="text-sm text-gray-300 mt-1">
                Imported {importResult.imported} items
                {importResult.skipped > 0 && `, skipped ${importResult.skipped}`}
              </p>
              {importResult.errors.length > 0 && (
                <p className="text-sm text-yellow-400 mt-1">
                  {importResult.errors.length} error(s)
                </p>
              )}
            </div>
            <button
              onClick={() => setImportResult(null)}
              className="text-gray-400 hover:text-white ml-4"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
