import { useEffect, useState, useCallback } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import {
  getWorkflow,
  startWorkflow,
  pauseWorkflow,
  advanceWorkflowStep,
  deleteWorkflow,
} from '../api'
import type { Workflow, ImportJsonlResponse } from '../api'
import WorkflowTimeline from '../components/workflow/WorkflowTimeline'
import StepCard from '../components/workflow/StepCard'
import PlanningChat from '../components/planning/PlanningChat'
import WorkflowEditor from '../components/workflow/WorkflowEditor'
import ImportJsonlModal from '../components/workflow/ImportJsonlModal'

export default function WorkflowDetail() {
  const { slug, workflowId } = useParams<{ slug: string; workflowId: string }>()
  const navigate = useNavigate()

  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState(false)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showEditor, setShowEditor] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [importResult, setImportResult] = useState<ImportJsonlResponse | null>(null)

  const loadWorkflow = useCallback(async () => {
    if (!slug || !workflowId) return
    try {
      const data = await getWorkflow(slug, workflowId)
      setWorkflow(data)
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

  const handleStart = async () => {
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

  const handlePause = async () => {
    if (!slug || !workflowId) return
    setActionLoading(true)
    try {
      const updated = await pauseWorkflow(slug, workflowId)
      setWorkflow(updated)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to pause workflow')
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

  const handleDelete = async () => {
    if (!slug || !workflowId) return
    setActionLoading(true)
    try {
      await deleteWorkflow(slug, workflowId)
      navigate(`/projects/${slug}/workflows`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete workflow')
      setActionLoading(false)
    }
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

  const currentStep = workflow.steps.find(s => s.step_number === workflow.current_step)
  const isInteractiveStep = currentStep?.step_type === 'interactive'
  const isAutonomousStep = currentStep?.step_type === 'autonomous'

  const statusColors: Record<string, string> = {
    draft: 'bg-gray-600',
    active: 'bg-green-600',
    paused: 'bg-yellow-600',
    completed: 'bg-blue-600',
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
            <span className={`px-3 py-1 rounded-full text-sm font-medium text-white ${statusColors[workflow.status]}`}>
              {workflow.status.charAt(0).toUpperCase() + workflow.status.slice(1)}
            </span>
          </div>

          <div className="flex items-center space-x-3">
            {workflow.status === 'draft' && (
              <button
                onClick={handleStart}
                disabled={actionLoading}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-500 transition-colors disabled:opacity-50"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Start Workflow</span>
              </button>
            )}

            {workflow.status === 'active' && (
              <button
                onClick={handlePause}
                disabled={actionLoading}
                className="flex items-center space-x-2 px-4 py-2 bg-yellow-600 text-white rounded hover:bg-yellow-500 transition-colors disabled:opacity-50"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <span>Pause</span>
              </button>
            )}

            {workflow.status === 'paused' && (
              <button
                onClick={handleStart}
                disabled={actionLoading}
                className="flex items-center space-x-2 px-4 py-2 bg-green-600 text-white rounded hover:bg-green-500 transition-colors disabled:opacity-50"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                </svg>
                <span>Resume</span>
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
              onClick={() => setShowEditor(true)}
              className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
              <span>Edit</span>
            </button>

            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
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

      {/* Timeline */}
      <div className="mb-8">
        <WorkflowTimeline
          steps={workflow.steps}
          currentStep={workflow.current_step}
        />
      </div>

      {/* Current Step Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2">
          {currentStep && (
            <div className="card">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-white">
                  Step {currentStep.step_number}: {currentStep.name}
                </h2>
                {currentStep.config?.skippable && currentStep.status === 'active' && (
                  <button
                    onClick={() => handleAdvance(true)}
                    disabled={actionLoading}
                    className="text-sm text-gray-400 hover:text-white"
                  >
                    Skip this step
                  </button>
                )}
              </div>

              {currentStep.config?.description && (
                <p className="text-gray-400 mb-6">{currentStep.config.description}</p>
              )}

              {/* Interactive Step: Show Chat */}
              {isInteractiveStep && currentStep.status === 'active' && (
                <PlanningChat
                  projectSlug={slug!}
                  workflowId={workflowId!}
                  onComplete={loadWorkflow}
                />
              )}

              {/* Autonomous Step: Show Loop Progress */}
              {isAutonomousStep && currentStep.status === 'active' && workflow.status === 'active' && (
                <div className="text-center py-8">
                  <div className="inline-flex items-center space-x-3 text-gray-400">
                    <svg className="w-6 h-6 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>Running autonomous step...</span>
                  </div>
                  {currentStep.loop_name && (
                    <p className="mt-4 text-sm text-gray-500">
                      Loop: {currentStep.loop_name}
                    </p>
                  )}
                </div>
              )}

              {/* Autonomous Step: Paused */}
              {isAutonomousStep && currentStep.status === 'active' && workflow.status === 'paused' && (
                <div className="text-center py-8">
                  <div className="inline-flex items-center space-x-3 text-yellow-400">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <span>Workflow paused</span>
                  </div>
                  {currentStep.loop_name && (
                    <p className="mt-4 text-sm text-gray-500">
                      Loop: {currentStep.loop_name}
                    </p>
                  )}
                </div>
              )}

              {/* Pending Step */}
              {currentStep.status === 'pending' && (
                <div className="text-center py-8 text-gray-400">
                  <p>This step hasn't started yet.</p>
                  {workflow.status === 'draft' && (
                    <button
                      onClick={handleStart}
                      className="mt-4 px-6 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 transition-colors"
                    >
                      Start Workflow
                    </button>
                  )}
                </div>
              )}

              {/* Completed Step */}
              {currentStep.status === 'completed' && (
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

        {/* Sidebar: All Steps */}
        <div className="space-y-4">
          <h3 className="text-lg font-semibold text-white">All Steps</h3>
          {workflow.steps.map((step) => (
            <StepCard
              key={step.id}
              step={step}
              isCurrent={step.step_number === workflow.current_step}
              onEdit={() => setShowEditor(true)}
            />
          ))}
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={() => setShowDeleteConfirm(false)}
          onKeyDown={(e) => e.key === 'Escape' && setShowDeleteConfirm(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="delete-dialog-title"
        >
          <div className="card max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 id="delete-dialog-title" className="text-xl font-semibold text-white mb-4">Delete Workflow?</h3>
            <p className="text-gray-400 mb-6">
              This will permanently delete the workflow "{workflow.name}" and all its steps.
              This action cannot be undone.
            </p>
            <div className="flex justify-end space-x-3">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={actionLoading}
                className="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-500 transition-colors disabled:opacity-50"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Workflow Editor Modal */}
      {showEditor && (
        <WorkflowEditor
          workflow={workflow}
          projectSlug={slug!}
          onClose={() => setShowEditor(false)}
          onSave={(updated) => {
            setWorkflow(updated)
            setShowEditor(false)
          }}
        />
      )}

      {/* Import JSONL Modal */}
      {showImport && (
        <ImportJsonlModal
          projectSlug={slug!}
          workflowId={workflowId!}
          steps={workflow.steps}
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
