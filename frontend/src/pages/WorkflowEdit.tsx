import { useEffect, useState, useCallback } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import {
  getWorkflow,
  updateWorkflow,
  createWorkflowStep,
  updateWorkflowStep,
  deleteWorkflowStep,
  reorderWorkflowSteps,
  listWorkflowResources,
  listProjectResources,
} from '../api'
import type { Workflow, WorkflowStep, WorkflowResource, ProjectResource } from '../api'
import EditorHeader from '../components/workflow/editor/EditorHeader'
import OverviewTab from '../components/workflow/editor/OverviewTab'
import StepsTab from '../components/workflow/editor/StepsTab'
import ResourcesTab from '../components/workflow/editor/ResourcesTab'
import SettingsTab from '../components/workflow/editor/SettingsTab'

type EditorTab = 'overview' | 'steps' | 'resources' | 'settings'

export default function WorkflowEdit() {
  const { slug, workflowId } = useParams<{ slug: string; workflowId: string }>()
  const navigate = useNavigate()

  // Data state
  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Edit state
  const [workflowName, setWorkflowName] = useState('')
  const [steps, setSteps] = useState<WorkflowStep[]>([])
  const [resources, setResources] = useState<WorkflowResource[]>([])
  const [projectResources, setProjectResources] = useState<ProjectResource[]>([])

  // UI state
  const [activeTab, setActiveTab] = useState<EditorTab>('overview')
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)

  // Load workflow data
  const loadWorkflow = useCallback(async () => {
    if (!slug || !workflowId) return
    try {
      const data = await getWorkflow(slug, workflowId)
      setWorkflow(data)
      setWorkflowName(data.name)
      setSteps([...data.steps])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workflow')
    } finally {
      setLoading(false)
    }
  }, [slug, workflowId])

  // Load resources
  const loadResources = useCallback(async () => {
    if (!slug || !workflowId || !workflow) return
    try {
      const [wfResources, projResources] = await Promise.all([
        listWorkflowResources(slug, workflow.id),
        listProjectResources(slug),
      ])
      setResources(wfResources)
      setProjectResources(projResources)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load resources')
    }
  }, [slug, workflowId, workflow])

  useEffect(() => {
    loadWorkflow()
  }, [loadWorkflow])

  useEffect(() => {
    if (workflow) {
      loadResources()
    }
  }, [workflow, loadResources])

  // Track dirty state
  useEffect(() => {
    if (!workflow) return
    const nameChanged = workflowName !== workflow.name
    const stepsChanged = JSON.stringify(steps) !== JSON.stringify(workflow.steps)
    setDirty(nameChanged || stepsChanged)
  }, [workflow, workflowName, steps])

  // Warn on navigation with unsaved changes
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault()
        e.returnValue = ''
      }
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [dirty])

  const handleSave = useCallback(async () => {
    if (!workflow || !slug) return
    setSaving(true)
    setError(null)

    try {
      // Update workflow name if changed
      if (workflowName !== workflow.name) {
        await updateWorkflow(slug, workflow.id, { name: workflowName })
      }

      // Determine which steps need to be created, updated, or deleted
      const originalStepIds = new Set(workflow.steps.map(s => s.id))
      const currentStepIds = new Set(steps.filter(s => s.id).map(s => s.id))

      // Delete removed steps
      for (const originalStep of workflow.steps) {
        if (!currentStepIds.has(originalStep.id)) {
          await deleteWorkflowStep(slug, workflow.id, originalStep.id)
        }
      }

      // Create new steps and update existing ones
      const finalStepIds: number[] = []
      for (let i = 0; i < steps.length; i++) {
        const step = steps[i]
        if (!step.id || !originalStepIds.has(step.id)) {
          // New step - create it
          const stepData: Parameters<typeof createWorkflowStep>[2] = {
            name: step.name,
            step_type: step.step_type,
            description: step.config?.description,
            skippable: step.config?.skippable,
            loop_type: step.config?.loopType,
          }
          if (step.step_type === 'autonomous') {
            stepData.model = step.config?.model
            stepData.timeout = step.config?.timeout
            stepData.allowed_tools = step.config?.allowedTools
            stepData.max_iterations = step.config?.max_iterations
            stepData.cooldown_between_iterations = step.config?.cooldown_between_iterations
            stepData.max_consecutive_errors = step.config?.max_consecutive_errors
          }
          const created = await createWorkflowStep(slug, workflow.id, stepData)
          finalStepIds.push(created.id)
        } else {
          // Existing step - update if changed
          const originalStep = workflow.steps.find(s => s.id === step.id)
          const configChanged = originalStep && (
            originalStep.name !== step.name ||
            originalStep.step_type !== step.step_type ||
            originalStep.config?.description !== step.config?.description ||
            originalStep.config?.skippable !== step.config?.skippable ||
            originalStep.config?.loopType !== step.config?.loopType ||
            originalStep.config?.model !== step.config?.model ||
            originalStep.config?.timeout !== step.config?.timeout ||
            JSON.stringify(originalStep.config?.allowedTools) !== JSON.stringify(step.config?.allowedTools) ||
            originalStep.config?.max_iterations !== step.config?.max_iterations ||
            originalStep.config?.cooldown_between_iterations !== step.config?.cooldown_between_iterations ||
            originalStep.config?.max_consecutive_errors !== step.config?.max_consecutive_errors
          )
          if (configChanged) {
            const updateData: Parameters<typeof updateWorkflowStep>[3] = {
              name: step.name,
              step_type: step.step_type,
              description: step.config?.description,
              skippable: step.config?.skippable,
              loop_type: step.config?.loopType,
            }
            if (step.step_type === 'autonomous') {
              updateData.model = step.config?.model
              updateData.timeout = step.config?.timeout
              updateData.allowed_tools = step.config?.allowedTools
              updateData.max_iterations = step.config?.max_iterations
              updateData.cooldown_between_iterations = step.config?.cooldown_between_iterations
              updateData.max_consecutive_errors = step.config?.max_consecutive_errors
            }
            await updateWorkflowStep(slug, workflow.id, step.id, updateData)
          }
          finalStepIds.push(step.id)
        }
      }

      // Reorder steps if order changed
      const originalOrder = workflow.steps.map(s => s.id)
      if (JSON.stringify(originalOrder) !== JSON.stringify(finalStepIds)) {
        await reorderWorkflowSteps(slug, workflow.id, finalStepIds)
      }

      // Refresh workflow data
      await loadWorkflow()
      setDirty(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save workflow')
    } finally {
      setSaving(false)
    }
  }, [workflow, slug, workflowName, steps, loadWorkflow])

  const handleBack = useCallback(() => {
    if (dirty) {
      const confirmed = window.confirm('You have unsaved changes. Are you sure you want to leave?')
      if (!confirmed) return
    }
    navigate(`/projects/${slug}/workflows/${workflowId}`)
  }, [dirty, navigate, slug, workflowId])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't handle shortcuts if a modal is open (check for fixed overlays)
      const hasOpenModal = document.querySelector('.fixed.inset-0.bg-black\\/50')
      if (hasOpenModal) return

      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        if (dirty && !saving) {
          handleSave()
        }
      }
      if (e.key === 'Escape') {
        handleBack()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [dirty, saving, handleSave, handleBack])

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading workflow...</div>
      </div>
    )
  }

  if (error && !workflow) {
    return (
      <div className="p-6">
        <div className="card bg-red-900/20 border border-red-800">
          <h2 className="text-lg font-semibold text-red-400 mb-2">Error</h2>
          <p className="text-gray-300">{error}</p>
          <Link to={`/projects/${slug}`} className="btn-secondary mt-4 inline-block">
            Back to Project
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

  const tabs: { key: EditorTab; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'steps', label: 'Steps' },
    { key: 'resources', label: 'Resources' },
    { key: 'settings', label: 'Settings' },
  ]

  return (
    <div className="min-h-screen">
      {/* Header */}
      <EditorHeader
        workflowName={workflowName}
        onBack={handleBack}
        onSave={handleSave}
        saving={saving}
        dirty={dirty}
      />

      {/* Error Banner */}
      {error && (
        <div className="mx-6 mt-4 p-4 rounded-lg bg-red-900/20 border border-red-800">
          <div className="flex items-center justify-between">
            <p className="text-red-400 text-sm">{error}</p>
            <button
              onClick={() => setError(null)}
              className="text-red-400 hover:text-red-300"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-700 px-6">
        <nav className="flex space-x-8">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === tab.key
                  ? 'border-primary-500 text-primary-400'
                  : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-500'
              }`}
            >
              {tab.label}
              {tab.key === 'steps' && ` (${steps.length})`}
              {tab.key === 'resources' && resources.length > 0 && ` (${resources.length})`}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="p-6">
        {activeTab === 'overview' && (
          <OverviewTab
            workflow={workflow}
            workflowName={workflowName}
            onNameChange={(name) => setWorkflowName(name)}
            steps={steps}
            resources={resources}
            onViewResources={() => setActiveTab('resources')}
          />
        )}

        {activeTab === 'steps' && (
          <StepsTab
            projectSlug={slug!}
            workflowId={workflow.id}
            steps={steps}
            onStepsChange={(newSteps) => setSteps(newSteps)}
            onError={(err) => setError(err)}
          />
        )}

        {activeTab === 'resources' && (
          <ResourcesTab
            projectSlug={slug!}
            workflowId={workflow.id}
            resources={resources}
            projectResources={projectResources}
            onResourcesChange={loadResources}
            onError={(err) => setError(err)}
          />
        )}

        {activeTab === 'settings' && (
          <SettingsTab
            workflow={workflow}
            projectSlug={slug!}
            onWorkflowUpdate={loadWorkflow}
            onError={(err) => setError(err)}
          />
        )}
      </div>
    </div>
  )
}
