import { useState, useCallback, useEffect } from 'react'
import type {
  Workflow,
  WorkflowStep,
  WorkflowResource,
  ProjectResource,
  StepResource,
  PreviewPromptResponse,
} from '../../api'
import {
  getWorkflow,
  updateWorkflow,
  createWorkflowStep,
  updateWorkflowStep,
  deleteWorkflowStep,
  reorderWorkflowSteps,
  listWorkflowResources,
  createWorkflowResource,
  updateWorkflowResource,
  deleteWorkflowResource,
  listProjectResources,
  importProjectResourceToWorkflow,
  listStepResources,
  createStepResource,
  deleteStepResource,
  disableInheritedResource,
  enableInheritedResource,
  previewStepPrompt,
} from '../../api'
import LoopPermissionEditor from '../LoopPermissionEditor'

interface WorkflowEditorProps {
  workflow: Workflow
  projectSlug: string
  onClose: () => void
  onSave: (workflow: Workflow) => void
}

interface EditingStep {
  id?: number
  name: string
  step_type: 'interactive' | 'autonomous'
  description: string
  skippable: boolean
  // New fields for autonomous steps
  loopType?: string
  model?: 'sonnet' | 'opus' | 'haiku'
  timeout?: number
  allowedTools?: string[]
  // Loop name for permission editing (only set for existing autonomous steps)
  loop_name?: string
}

type EditorTab = 'steps' | 'resources'
type StepEditorTab = 'settings' | 'resources' | 'permissions'
type ToolsPreset = 'none' | 'web-only' | 'all' | 'custom'

const TOOLS_PRESETS: Record<Exclude<ToolsPreset, 'custom'>, string[]> = {
  'none': [],
  'web-only': ['WebSearch', 'WebFetch'],
  'all': ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep', 'WebSearch', 'WebFetch', 'NotebookEdit'],
}

function getToolsPreset(tools?: string[]): ToolsPreset {
  if (!tools || tools.length === 0) return 'none'
  if (tools.length === 2 && tools.includes('WebSearch') && tools.includes('WebFetch')) return 'web-only'
  // Check if tools exactly match the 'all' preset (order-independent)
  const allPreset = new Set(TOOLS_PRESETS['all'])
  const currentTools = new Set(tools)
  if (allPreset.size === currentTools.size && tools.every(t => allPreset.has(t))) return 'all'
  return 'custom'
}

export default function WorkflowEditor({
  workflow,
  projectSlug,
  onClose,
  onSave,
}: WorkflowEditorProps) {
  const [workflowName, setWorkflowName] = useState(workflow.name)
  const [steps, setSteps] = useState<WorkflowStep[]>([...workflow.steps])
  const [editingStep, setEditingStep] = useState<EditingStep | null>(null)
  const [editingStepIndex, setEditingStepIndex] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Tab state
  const [activeTab, setActiveTab] = useState<EditorTab>('steps')

  // Resources state
  const [resources, setResources] = useState<WorkflowResource[]>([])
  const [projectResources, setProjectResources] = useState<ProjectResource[]>([])
  const [resourcesLoading, setResourcesLoading] = useState(false)
  const [resourceOperationPending, setResourceOperationPending] = useState(false)
  const [showAddResourceModal, setShowAddResourceModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [editingResource, setEditingResource] = useState<WorkflowResource | null>(null)
  const [editResourceContent, setEditResourceContent] = useState('')
  const [newResource, setNewResource] = useState({
    name: '',
    resource_type: 'guardrail',
    content: '',
  })

  // Permission editor state
  const [showPermissionEditor, setShowPermissionEditor] = useState(false)
  const [permissionEditLoopName, setPermissionEditLoopName] = useState<string | null>(null)

  // Step editor tab state (for expanded step modal)
  const [stepEditorTab, setStepEditorTab] = useState<StepEditorTab>('settings')

  // Step resources state
  const [stepResources, setStepResources] = useState<StepResource[]>([])
  const [stepResourcesLoading, setStepResourcesLoading] = useState(false)
  const [stepResourceOperationPending, setStepResourceOperationPending] = useState(false)
  const [showAddStepResourceModal, setShowAddStepResourceModal] = useState(false)
  const [newStepResource, setNewStepResource] = useState({
    name: '',
    resource_type: 'guardrail',
    content: '',
  })

  // Prompt preview state
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [previewData, setPreviewData] = useState<PreviewPromptResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // Load resources when switching to resources tab
  const loadResources = useCallback(async () => {
    setResourcesLoading(true)
    try {
      const [wfResources, projResources] = await Promise.all([
        listWorkflowResources(projectSlug, workflow.id),
        listProjectResources(projectSlug),
      ])
      setResources(wfResources)
      setProjectResources(projResources)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load resources')
    } finally {
      setResourcesLoading(false)
    }
  }, [projectSlug, workflow.id])

  useEffect(() => {
    if (activeTab === 'resources') {
      loadResources()
    }
  }, [activeTab, loadResources])

  // Load step resources when editing a saved autonomous step and switching to resources tab
  const loadStepResources = useCallback(async (stepId: number) => {
    setStepResourcesLoading(true)
    try {
      const [stepRes, wfRes] = await Promise.all([
        listStepResources(projectSlug, workflow.id, stepId),
        listWorkflowResources(projectSlug, workflow.id),
      ])
      setStepResources(stepRes)
      setResources(wfRes)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load step resources')
    } finally {
      setStepResourcesLoading(false)
    }
  }, [projectSlug, workflow.id])

  // Load step resources when step editor tab changes to 'resources'
  useEffect(() => {
    if (stepEditorTab === 'resources' && editingStep?.id) {
      loadStepResources(editingStep.id)
    }
  }, [stepEditorTab, editingStep?.id, loadStepResources])

  // Handle disabling/enabling inherited resources
  const handleToggleInheritedResource = async (workflowResource: WorkflowResource) => {
    if (!editingStep?.id || stepResourceOperationPending) return

    setStepResourceOperationPending(true)
    try {
      // Check if already disabled
      const existingDisable = stepResources.find(
        sr => sr.workflow_resource_id === workflowResource.id && sr.mode === 'disable'
      )

      if (existingDisable) {
        // Re-enable by deleting the disable record
        await enableInheritedResource(projectSlug, workflow.id, editingStep.id, workflowResource.id)
      } else {
        // Disable the inherited resource
        await disableInheritedResource(projectSlug, workflow.id, editingStep.id, workflowResource.id)
      }
      await loadStepResources(editingStep.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle resource')
    } finally {
      setStepResourceOperationPending(false)
    }
  }

  // Check if a workflow resource is disabled for this step
  const isResourceDisabled = (workflowResourceId: number): boolean => {
    return stepResources.some(
      sr => sr.workflow_resource_id === workflowResourceId && sr.mode === 'disable'
    )
  }

  // Handle adding a step-specific resource
  const handleAddStepResource = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingStep?.id || !newStepResource.name.trim() || !newStepResource.content.trim()) return
    if (stepResourceOperationPending) return

    setStepResourceOperationPending(true)
    try {
      await createStepResource(projectSlug, workflow.id, editingStep.id, {
        mode: 'add',
        resource_type: newStepResource.resource_type,
        name: newStepResource.name.trim(),
        content: newStepResource.content.trim(),
      })
      setNewStepResource({ name: '', resource_type: 'guardrail', content: '' })
      setShowAddStepResourceModal(false)
      await loadStepResources(editingStep.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add step resource')
    } finally {
      setStepResourceOperationPending(false)
    }
  }

  // Handle deleting a step resource
  const handleDeleteStepResource = async (resource: StepResource) => {
    if (!editingStep?.id || stepResourceOperationPending) return
    if (!confirm(`Delete this step resource?`)) return

    setStepResourceOperationPending(true)
    try {
      await deleteStepResource(projectSlug, workflow.id, editingStep.id, resource.id)
      await loadStepResources(editingStep.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete step resource')
    } finally {
      setStepResourceOperationPending(false)
    }
  }

  // Handle preview prompt
  const handlePreviewPrompt = async () => {
    if (!editingStep?.id) return

    setPreviewLoading(true)
    try {
      const preview = await previewStepPrompt(projectSlug, workflow.id, editingStep.id)
      setPreviewData(preview)
      setShowPreviewModal(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load preview')
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleSave = useCallback(async () => {
    setSaving(true)
    setError(null)

    try {
      // Update workflow name if changed
      if (workflowName !== workflow.name) {
        await updateWorkflow(projectSlug, workflow.id, { name: workflowName })
      }

      // Determine which steps need to be created, updated, or deleted
      const originalStepIds = new Set(workflow.steps.map(s => s.id))
      const currentStepIds = new Set(steps.filter(s => s.id).map(s => s.id))

      // Delete removed steps
      for (const originalStep of workflow.steps) {
        if (!currentStepIds.has(originalStep.id)) {
          await deleteWorkflowStep(projectSlug, workflow.id, originalStep.id)
        }
      }

      // Create new steps and update existing ones
      // Track the final step IDs in display order (new steps get their created IDs)
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
          // Include autonomous config fields only for autonomous steps
          if (step.step_type === 'autonomous') {
            stepData.model = step.config?.model
            stepData.timeout = step.config?.timeout
            stepData.allowed_tools = step.config?.allowedTools
          }
          const created = await createWorkflowStep(projectSlug, workflow.id, stepData)
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
            JSON.stringify(originalStep.config?.allowedTools) !== JSON.stringify(step.config?.allowedTools)
          )
          if (configChanged) {
            const updateData: Parameters<typeof updateWorkflowStep>[3] = {
              name: step.name,
              step_type: step.step_type,
              description: step.config?.description,
              skippable: step.config?.skippable,
              loop_type: step.config?.loopType,
            }
            // Include autonomous config fields only for autonomous steps
            if (step.step_type === 'autonomous') {
              updateData.model = step.config?.model
              updateData.timeout = step.config?.timeout
              updateData.allowed_tools = step.config?.allowedTools
            }
            await updateWorkflowStep(projectSlug, workflow.id, step.id, updateData)
          }
          finalStepIds.push(step.id)
        }
      }

      // Reorder steps if order changed
      const originalOrder = workflow.steps.map(s => s.id)
      if (JSON.stringify(originalOrder) !== JSON.stringify(finalStepIds)) {
        await reorderWorkflowSteps(projectSlug, workflow.id, finalStepIds)
      }

      // Always fetch fresh workflow data to ensure we have the latest state
      const refreshedWorkflow = await getWorkflow(projectSlug, workflow.id)
      onSave(refreshedWorkflow)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save workflow')
    } finally {
      setSaving(false)
    }
  }, [workflow, workflowName, steps, projectSlug, onSave])

  const handleAddStep = () => {
    setEditingStep({
      name: '',
      step_type: 'autonomous',
      description: '',
      skippable: false,
      // Defaults for autonomous steps
      loopType: 'implementation',
      model: 'sonnet',
      timeout: 300,
      allowedTools: [],
    })
    setEditingStepIndex(steps.length)
    // Reset step editor tab to settings
    setStepEditorTab('settings')
    // Clear step resources state (new step won't have resources)
    setStepResources([])
  }

  const handleEditStep = (index: number) => {
    const step = steps[index]
    setEditingStep({
      id: step.id,
      name: step.name,
      step_type: step.step_type,
      description: step.config?.description || '',
      skippable: step.config?.skippable || false,
      // Load autonomous config
      loopType: step.config?.loopType || 'implementation',
      model: (step.config?.model as 'sonnet' | 'opus' | 'haiku') || 'sonnet',
      timeout: step.config?.timeout || 300,
      allowedTools: step.config?.allowedTools || [],
      // Include loop_name for permission editing
      loop_name: step.loop_name,
    })
    setEditingStepIndex(index)
    // Reset step editor tab to settings
    setStepEditorTab('settings')
    // Clear step resources state
    setStepResources([])
  }

  const handleSaveStep = () => {
    if (!editingStep || editingStepIndex === null) return

    // Build config - only include autonomous fields for autonomous steps
    const config: WorkflowStep['config'] = {
      description: editingStep.description,
      skippable: editingStep.skippable,
    }

    if (editingStep.step_type === 'autonomous') {
      config.loopType = editingStep.loopType
      config.model = editingStep.model
      config.timeout = editingStep.timeout
      config.allowedTools = editingStep.allowedTools
    }

    const newStep: WorkflowStep = {
      id: editingStep.id || 0,
      workflow_id: workflow.id,
      step_number: editingStepIndex + 1,
      name: editingStep.name,
      step_type: editingStep.step_type,
      status: 'pending',
      config,
    }

    const newSteps = [...steps]
    if (editingStepIndex < steps.length) {
      newSteps[editingStepIndex] = newStep
    } else {
      newSteps.push(newStep)
    }
    setSteps(newSteps)
    setEditingStep(null)
    setEditingStepIndex(null)
  }

  const handleDeleteStep = (index: number) => {
    const newSteps = steps.filter((_, i) => i !== index)
    setSteps(newSteps)
  }

  const handleMoveStep = (index: number, direction: 'up' | 'down') => {
    const newIndex = direction === 'up' ? index - 1 : index + 1
    if (newIndex < 0 || newIndex >= steps.length) return

    const newSteps = [...steps]
    const [moved] = newSteps.splice(index, 1)
    newSteps.splice(newIndex, 0, moved)
    setSteps(newSteps)
  }

  // Resource handlers
  const handleAddResource = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newResource.name.trim() || !newResource.content.trim()) return
    if (resourceOperationPending) return

    setResourceOperationPending(true)
    try {
      await createWorkflowResource(projectSlug, workflow.id, {
        name: newResource.name.trim(),
        resource_type: newResource.resource_type,
        content: newResource.content.trim(),
        source: 'manual',
      })
      setNewResource({ name: '', resource_type: 'guardrail', content: '' })
      setShowAddResourceModal(false)
      await loadResources()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add resource')
    } finally {
      setResourceOperationPending(false)
    }
  }

  const handleImportResource = async (projectResource: ProjectResource) => {
    if (resourceOperationPending) return

    setResourceOperationPending(true)
    try {
      await importProjectResourceToWorkflow(projectSlug, workflow.id, projectResource.id)
      setShowImportModal(false)
      await loadResources()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import resource')
    } finally {
      setResourceOperationPending(false)
    }
  }

  const handleToggleResource = async (resource: WorkflowResource) => {
    if (resourceOperationPending) return

    setResourceOperationPending(true)
    try {
      await updateWorkflowResource(projectSlug, workflow.id, resource.id, {
        enabled: !resource.enabled,
      })
      await loadResources()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update resource')
    } finally {
      setResourceOperationPending(false)
    }
  }

  const handleSaveResourceEdit = async () => {
    if (!editingResource) return
    if (resourceOperationPending) return

    setResourceOperationPending(true)
    try {
      await updateWorkflowResource(projectSlug, workflow.id, editingResource.id, {
        content: editResourceContent,
      })
      setEditingResource(null)
      await loadResources()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save resource')
    } finally {
      setResourceOperationPending(false)
    }
  }

  const handleDeleteResource = async (resource: WorkflowResource) => {
    if (!confirm(`Delete "${resource.name}"? This cannot be undone.`)) return
    if (resourceOperationPending) return

    setResourceOperationPending(true)
    try {
      await deleteWorkflowResource(projectSlug, workflow.id, resource.id)
      await loadResources()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete resource')
    } finally {
      setResourceOperationPending(false)
    }
  }

  const getResourceTypeLabel = (type: string) => {
    switch (type) {
      case 'design_doc': return 'Design Document'
      case 'guardrail': return 'Guardrail'
      case 'input_file': return 'Input File'
      case 'prompt': return 'Prompt'
      default: return type
    }
  }

  const getResourceTypeIcon = (type: string) => {
    switch (type) {
      case 'design_doc': return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      )
      case 'guardrail': return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      )
      default: return (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
      )
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl border border-gray-700 w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-700">
          <h2 className="text-xl font-semibold text-white">Edit Workflow</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
            aria-label="Close"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-400">
              {error}
            </div>
          )}

          {/* Workflow Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Workflow Name
            </label>
            <input
              type="text"
              value={workflowName}
              onChange={(e) => setWorkflowName(e.target.value)}
              className="w-full px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500"
              placeholder="Enter workflow name"
            />
          </div>

          {/* Tabs */}
          <div className="flex space-x-1 border-b border-gray-700">
            <button
              onClick={() => {
                setActiveTab('steps')
                setError(null)
              }}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === 'steps'
                  ? 'border-primary-500 text-white'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Steps ({steps.length})
            </button>
            <button
              onClick={() => {
                setActiveTab('resources')
                setError(null)
              }}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === 'resources'
                  ? 'border-primary-500 text-white'
                  : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              Resources {resources.length > 0 && `(${resources.length})`}
            </button>
          </div>

          {/* Steps Tab */}
          {activeTab === 'steps' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <label className="block text-sm font-medium text-gray-300">
                  Workflow Steps
                </label>
                <button
                  onClick={handleAddStep}
                  className="flex items-center space-x-1 text-sm text-primary-400 hover:text-primary-300"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  <span>Add Step</span>
                </button>
              </div>

              {steps.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  No steps yet. Add a step to get started.
                </div>
              ) : (
                <div className="space-y-2">
                  {steps.map((step, index) => (
                    <div
                      key={step.id ? `step-${step.id}` : `new-${index}`}
                      className="flex items-center space-x-3 p-3 bg-gray-800 rounded-lg border border-gray-700"
                    >
                      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-600/20 text-primary-400 flex items-center justify-center text-sm font-medium">
                        {index + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-white truncate">{step.name}</div>
                        <div className="text-xs text-gray-400">
                          {step.step_type === 'interactive' ? 'Interactive' : 'Autonomous'}
                          {step.config?.loopType && step.step_type === 'autonomous' && ` (${step.config.loopType})`}
                          {step.config?.model && step.step_type === 'autonomous' && ` - ${step.config.model}`}
                          {step.config?.description && ` - ${step.config.description}`}
                        </div>
                      </div>
                      <div className="flex items-center space-x-1">
                        <button
                          onClick={() => handleMoveStep(index, 'up')}
                          disabled={index === 0}
                          className="p-1 text-gray-400 hover:text-white disabled:opacity-30"
                          aria-label="Move up"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleMoveStep(index, 'down')}
                          disabled={index === steps.length - 1}
                          className="p-1 text-gray-400 hover:text-white disabled:opacity-30"
                          aria-label="Move down"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleEditStep(index)}
                          className="p-1 text-gray-400 hover:text-white"
                          aria-label="Edit"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDeleteStep(index)}
                          className="p-1 text-gray-400 hover:text-red-400"
                          aria-label="Delete"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Resources Tab */}
          {activeTab === 'resources' && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <label className="block text-sm font-medium text-gray-300">
                  Workflow Resources
                </label>
                <div className="flex space-x-2">
                  <button
                    onClick={() => setShowImportModal(true)}
                    className="flex items-center space-x-1 text-sm text-gray-400 hover:text-gray-300"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                    </svg>
                    <span>Import</span>
                  </button>
                  <button
                    onClick={() => setShowAddResourceModal(true)}
                    className="flex items-center space-x-1 text-sm text-primary-400 hover:text-primary-300"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    <span>Add Resource</span>
                  </button>
                </div>
              </div>

              {resourcesLoading ? (
                <div className="text-center py-8 text-gray-500">
                  Loading resources...
                </div>
              ) : resources.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <p>No resources attached to this workflow.</p>
                  <p className="text-sm mt-2">
                    Add design docs, guardrails, or other context for Claude.
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  {resources.map((resource) => (
                    <div
                      key={resource.id}
                      className="flex items-start space-x-3 p-3 bg-gray-800 rounded-lg border border-gray-700"
                    >
                      <div className={`p-2 rounded ${resource.enabled ? 'bg-primary-500/20 text-primary-400' : 'bg-gray-700 text-gray-500'}`}>
                        {getResourceTypeIcon(resource.resource_type)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-white truncate">{resource.name}</div>
                        <div className="text-xs text-gray-400">
                          {getResourceTypeLabel(resource.resource_type)}
                          {resource.source && ` - ${resource.source}`}
                        </div>
                        {resource.content && (
                          <p className="text-xs text-gray-500 mt-1 line-clamp-1">
                            {resource.content.length > 100
                              ? `${resource.content.slice(0, 100)}...`
                              : resource.content}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center space-x-1">
                        <button
                          onClick={() => handleToggleResource(resource)}
                          disabled={resourceOperationPending}
                          className={`px-2 py-1 text-xs rounded disabled:opacity-50 ${
                            resource.enabled
                              ? 'bg-green-600/20 text-green-400'
                              : 'bg-gray-700 text-gray-500'
                          }`}
                        >
                          {resource.enabled ? 'On' : 'Off'}
                        </button>
                        <button
                          onClick={() => {
                            setEditingResource(resource)
                            setEditResourceContent(resource.content || '')
                          }}
                          disabled={resourceOperationPending}
                          className="p-1 text-gray-400 hover:text-white disabled:opacity-50"
                          aria-label="Edit"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                          </svg>
                        </button>
                        <button
                          onClick={() => handleDeleteResource(resource)}
                          disabled={resourceOperationPending}
                          className="p-1 text-gray-400 hover:text-red-400 disabled:opacity-50"
                          aria-label="Delete"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end space-x-3 p-6 border-t border-gray-700">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !workflowName.trim()}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>

        {/* Step Editor Modal - Large with Tabs */}
        {editingStep && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-10">
            <div className="bg-gray-800 rounded-xl border border-gray-600 w-full max-w-5xl mx-4 max-h-[90vh] flex flex-col">
              {/* Modal Header */}
              <div className="flex items-center justify-between p-6 border-b border-gray-600 flex-shrink-0">
                <h3 className="text-lg font-semibold text-white">
                  {editingStep.id ? 'Edit Step' : 'Add Step'}
                </h3>
                <button
                  onClick={() => {
                    setEditingStep(null)
                    setEditingStepIndex(null)
                  }}
                  className="text-gray-400 hover:text-white"
                  aria-label="Close"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              {/* Tab Navigation (only show tabs for autonomous steps with an ID) */}
              {editingStep.step_type === 'autonomous' && (
                <div className="flex space-x-1 border-b border-gray-600 px-6 flex-shrink-0">
                  <button
                    onClick={() => setStepEditorTab('settings')}
                    className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                      stepEditorTab === 'settings'
                        ? 'border-primary-500 text-white'
                        : 'border-transparent text-gray-400 hover:text-gray-300'
                    }`}
                  >
                    Settings
                  </button>
                  <button
                    onClick={() => setStepEditorTab('resources')}
                    disabled={!editingStep.id}
                    className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                      stepEditorTab === 'resources'
                        ? 'border-primary-500 text-white'
                        : 'border-transparent text-gray-400 hover:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed'
                    }`}
                  >
                    Resources
                    {!editingStep.id && (
                      <span className="ml-1 text-xs text-gray-500">(save first)</span>
                    )}
                  </button>
                  <button
                    onClick={() => setStepEditorTab('permissions')}
                    disabled={!editingStep.id}
                    className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                      stepEditorTab === 'permissions'
                        ? 'border-primary-500 text-white'
                        : 'border-transparent text-gray-400 hover:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed'
                    }`}
                  >
                    Permissions
                    {!editingStep.id && (
                      <span className="ml-1 text-xs text-gray-500">(save first)</span>
                    )}
                  </button>
                </div>
              )}

              {/* Modal Content */}
              <div className="flex-1 overflow-y-auto p-6">
                {/* Settings Tab */}
                {(stepEditorTab === 'settings' || editingStep.step_type === 'interactive') && (
                  <div className="space-y-4 max-w-2xl">
                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-1">
                        Step Name
                      </label>
                      <input
                        type="text"
                        value={editingStep.name}
                        onChange={(e) => setEditingStep({ ...editingStep, name: e.target.value })}
                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500"
                        placeholder="e.g., Planning, Implementation"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-1">
                        Step Type
                      </label>
                      <select
                        value={editingStep.step_type}
                        onChange={(e) => setEditingStep({ ...editingStep, step_type: e.target.value as 'interactive' | 'autonomous' })}
                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      >
                        <option value="interactive">Interactive (Chat-based)</option>
                        <option value="autonomous">Autonomous (Loop-based)</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-300 mb-1">
                        Description
                      </label>
                      <textarea
                        value={editingStep.description}
                        onChange={(e) => setEditingStep({ ...editingStep, description: e.target.value })}
                        className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500 h-20 resize-none"
                        placeholder="What does this step do?"
                      />
                    </div>

                    <div className="flex items-center space-x-2">
                      <input
                        type="checkbox"
                        id="skippable"
                        checked={editingStep.skippable}
                        onChange={(e) => setEditingStep({ ...editingStep, skippable: e.target.checked })}
                        className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-primary-600 focus:ring-primary-500"
                      />
                      <label htmlFor="skippable" className="text-sm text-gray-300">
                        Allow skipping this step
                      </label>
                    </div>

                    {/* Autonomous Step Execution Settings */}
                    {editingStep.step_type === 'autonomous' && (
                      <div className="border-t border-gray-600 pt-4 mt-4 space-y-4">
                        <div className="text-sm font-medium text-gray-300 mb-2">
                          Execution Settings
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium text-gray-400 mb-1">
                              Loop Type
                            </label>
                            <select
                              value={editingStep.loopType || 'implementation'}
                              onChange={(e) => setEditingStep({ ...editingStep, loopType: e.target.value })}
                              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                            >
                              <option value="planning">Planning</option>
                              <option value="implementation">Implementation</option>
                              <option value="review">Review</option>
                              <option value="custom">Custom</option>
                            </select>
                          </div>

                          <div>
                            <label className="block text-sm font-medium text-gray-400 mb-1">
                              Model
                            </label>
                            <select
                              value={editingStep.model || 'sonnet'}
                              onChange={(e) => setEditingStep({ ...editingStep, model: e.target.value as 'sonnet' | 'opus' | 'haiku' })}
                              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                            >
                              <option value="sonnet">Sonnet (Balanced)</option>
                              <option value="opus">Opus (Most Capable)</option>
                              <option value="haiku">Haiku (Fast)</option>
                            </select>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-sm font-medium text-gray-400 mb-1">
                              Tools
                            </label>
                            <select
                              value={getToolsPreset(editingStep.allowedTools)}
                              onChange={(e) => {
                                const preset = e.target.value as ToolsPreset
                                if (preset !== 'custom') {
                                  setEditingStep({ ...editingStep, allowedTools: TOOLS_PRESETS[preset] })
                                }
                              }}
                              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                            >
                              <option value="none">None (Read-only)</option>
                              <option value="web-only">Web Only (Search + Fetch)</option>
                              <option value="all">All Tools</option>
                              {getToolsPreset(editingStep.allowedTools) === 'custom' && (
                                <option value="custom">Custom ({editingStep.allowedTools?.length || 0} tools)</option>
                              )}
                            </select>
                          </div>

                          <div>
                            <label className="block text-sm font-medium text-gray-400 mb-1">
                              Timeout (seconds)
                            </label>
                            <input
                              type="number"
                              value={editingStep.timeout || 300}
                              onChange={(e) => setEditingStep({ ...editingStep, timeout: parseInt(e.target.value) || 300 })}
                              min={60}
                              max={7200}
                              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                            />
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* Resources Tab (Autonomous only) */}
                {stepEditorTab === 'resources' && editingStep.step_type === 'autonomous' && editingStep.id && (
                  <div className="space-y-6">
                    {/* Inherited Resources from Workflow */}
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-sm font-medium text-gray-300">Inherited from Workflow</h4>
                        <button
                          onClick={handlePreviewPrompt}
                          disabled={previewLoading}
                          className="flex items-center space-x-1 text-sm text-primary-400 hover:text-primary-300 disabled:opacity-50"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                          </svg>
                          <span>{previewLoading ? 'Loading...' : 'Preview Prompt'}</span>
                        </button>
                      </div>

                      {stepResourcesLoading ? (
                        <div className="text-center py-4 text-gray-500">Loading resources...</div>
                      ) : resources.length === 0 ? (
                        <div className="text-center py-4 text-gray-500">
                          No workflow resources. Add resources in the Resources tab.
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {resources.map((wr) => {
                            const disabled = isResourceDisabled(wr.id)
                            return (
                              <div
                                key={wr.id}
                                className={`flex items-center justify-between p-3 rounded-lg border ${
                                  disabled
                                    ? 'bg-gray-800/50 border-gray-700 opacity-60'
                                    : 'bg-gray-700 border-gray-600'
                                }`}
                              >
                                <div className="flex items-center space-x-3">
                                  <div className={`p-2 rounded ${disabled ? 'bg-gray-700 text-gray-500' : 'bg-primary-500/20 text-primary-400'}`}>
                                    {getResourceTypeIcon(wr.resource_type)}
                                  </div>
                                  <div>
                                    <div className={`font-medium ${disabled ? 'text-gray-500' : 'text-white'}`}>
                                      {wr.name}
                                    </div>
                                    <div className="text-xs text-gray-500">
                                      {getResourceTypeLabel(wr.resource_type)}
                                      {disabled && ' — disabled for this step'}
                                    </div>
                                  </div>
                                </div>
                                <button
                                  onClick={() => handleToggleInheritedResource(wr)}
                                  disabled={stepResourceOperationPending}
                                  className={`px-3 py-1 text-xs rounded transition-colors ${
                                    disabled
                                      ? 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                                      : 'bg-green-600/20 text-green-400 hover:bg-green-600/30'
                                  }`}
                                >
                                  {disabled ? 'Enable' : 'Enabled'}
                                </button>
                              </div>
                            )
                          })}
                        </div>
                      )}
                    </div>

                    {/* Step-Specific Resources */}
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <h4 className="text-sm font-medium text-gray-300">Step-Specific Resources</h4>
                        <button
                          onClick={() => setShowAddStepResourceModal(true)}
                          className="flex items-center space-x-1 text-sm text-primary-400 hover:text-primary-300"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                          </svg>
                          <span>Add Resource</span>
                        </button>
                      </div>

                      {stepResources.filter(sr => sr.mode === 'add').length === 0 ? (
                        <div className="text-center py-4 text-gray-500 text-sm">
                          No step-specific resources. These are additional resources only used by this step.
                        </div>
                      ) : (
                        <div className="space-y-2">
                          {stepResources.filter(sr => sr.mode === 'add').map((sr) => (
                            <div
                              key={sr.id}
                              className="flex items-center justify-between p-3 bg-gray-700 rounded-lg border border-gray-600"
                            >
                              <div className="flex items-center space-x-3">
                                <div className="p-2 rounded bg-blue-500/20 text-blue-400">
                                  {getResourceTypeIcon(sr.resource_type || 'custom')}
                                </div>
                                <div>
                                  <div className="font-medium text-white">{sr.name}</div>
                                  <div className="text-xs text-gray-500">
                                    {getResourceTypeLabel(sr.resource_type || 'custom')} — step-specific
                                  </div>
                                </div>
                              </div>
                              <button
                                onClick={() => handleDeleteStepResource(sr)}
                                disabled={stepResourceOperationPending}
                                className="p-1 text-gray-400 hover:text-red-400 disabled:opacity-50"
                                aria-label="Delete"
                              >
                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Permissions Tab (Autonomous only) */}
                {stepEditorTab === 'permissions' && editingStep.step_type === 'autonomous' && editingStep.id && (
                  <div className="max-w-2xl">
                    {editingStep.loop_name ? (
                      <div className="space-y-4">
                        <p className="text-sm text-gray-400">
                          Configure which tools and file operations Claude can use during this step's execution.
                        </p>
                        <button
                          type="button"
                          onClick={() => {
                            setPermissionEditLoopName(editingStep.loop_name || null)
                            setShowPermissionEditor(true)
                          }}
                          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                          </svg>
                          <span>Edit Claude Code Permissions</span>
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-start space-x-3 p-4 bg-gray-700 rounded-lg">
                        <svg className="w-5 h-5 text-gray-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div>
                          <p className="text-sm text-gray-300">Permissions can be configured after the loop is created.</p>
                          <p className="mt-1 text-xs text-gray-500">
                            Start the workflow to create the loop, then return here to configure permissions.
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Modal Footer */}
              <div className="flex justify-end space-x-3 p-6 border-t border-gray-600 flex-shrink-0">
                <button
                  onClick={() => {
                    setEditingStep(null)
                    setEditingStepIndex(null)
                  }}
                  className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveStep}
                  disabled={!editingStep.name.trim()}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
                >
                  {editingStep.id ? 'Update Step' : 'Add Step'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Add Step Resource Modal */}
        {showAddStepResourceModal && editingStep?.id && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20">
            <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 w-full max-w-lg mx-4 max-h-[80vh] overflow-y-auto">
              <h3 className="text-lg font-semibold text-white mb-4">Add Step Resource</h3>

              <form onSubmit={handleAddStepResource} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Resource Type
                  </label>
                  <select
                    value={newStepResource.resource_type}
                    onChange={(e) => setNewStepResource({ ...newStepResource, resource_type: e.target.value })}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  >
                    <option value="guardrail">Guardrail</option>
                    <option value="design_doc">Design Document</option>
                    <option value="input_file">Input File</option>
                    <option value="prompt">Prompt</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Name
                  </label>
                  <input
                    type="text"
                    value={newStepResource.name}
                    onChange={(e) => setNewStepResource({ ...newStepResource, name: e.target.value })}
                    placeholder="e.g., Step-Specific Guidelines"
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Content
                  </label>
                  <textarea
                    value={newStepResource.content}
                    onChange={(e) => setNewStepResource({ ...newStepResource, content: e.target.value })}
                    placeholder="Resource content..."
                    rows={8}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500 font-mono text-sm resize-none"
                  />
                </div>

                <div className="flex justify-end space-x-3 mt-6">
                  <button
                    type="button"
                    onClick={() => setShowAddStepResourceModal(false)}
                    className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!newStepResource.name.trim() || !newStepResource.content.trim() || stepResourceOperationPending}
                    className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
                  >
                    {stepResourceOperationPending ? 'Adding...' : 'Add Resource'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Preview Prompt Modal */}
        {showPreviewModal && previewData && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20">
            <div className="bg-gray-800 rounded-xl border border-gray-600 w-full max-w-4xl mx-4 max-h-[90vh] flex flex-col">
              <div className="flex items-center justify-between p-6 border-b border-gray-600">
                <div>
                  <h3 className="text-lg font-semibold text-white">Prompt Preview</h3>
                  <p className="text-sm text-gray-400 mt-1">
                    {previewData.resources_used.length} resources • ~{previewData.total_tokens_estimate.toLocaleString()} tokens
                  </p>
                </div>
                <button
                  onClick={() => setShowPreviewModal(false)}
                  className="text-gray-400 hover:text-white"
                  aria-label="Close"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-6 space-y-4">
                {previewData.prompt_sections.length === 0 ? (
                  <div className="text-center py-8 text-gray-500">
                    No resources will be injected for this step.
                  </div>
                ) : (
                  previewData.prompt_sections.map((section, idx) => (
                    <div key={idx} className="border border-gray-600 rounded-lg overflow-hidden">
                      <div className="flex items-center justify-between px-4 py-2 bg-gray-700 border-b border-gray-600">
                        <div className="flex items-center space-x-2">
                          <span className="text-sm font-medium text-white">{section.resource_name}</span>
                          <span className="text-xs bg-gray-600 text-gray-300 px-2 py-0.5 rounded">
                            {section.resource_type}
                          </span>
                        </div>
                        <span className="text-xs text-gray-500">{section.position}</span>
                      </div>
                      <pre className="p-4 text-sm text-gray-300 overflow-x-auto bg-gray-900 max-h-64">
                        {section.content.length > 2000
                          ? section.content.slice(0, 2000) + '\n... (truncated)'
                          : section.content}
                      </pre>
                    </div>
                  ))
                )}
              </div>

              <div className="flex justify-end p-6 border-t border-gray-600">
                <button
                  onClick={() => setShowPreviewModal(false)}
                  className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Add Resource Modal */}
        {showAddResourceModal && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
            <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 w-full max-w-lg mx-4 max-h-[80vh] overflow-y-auto">
              <h3 className="text-lg font-semibold text-white mb-4">Add Resource</h3>

              <form onSubmit={handleAddResource} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Resource Type
                  </label>
                  <select
                    value={newResource.resource_type}
                    onChange={(e) => setNewResource({ ...newResource, resource_type: e.target.value })}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  >
                    <option value="guardrail">Guardrail</option>
                    <option value="design_doc">Design Document</option>
                    <option value="input_file">Input File</option>
                    <option value="prompt">Prompt</option>
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
                    placeholder="e.g., Code Style Guidelines"
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500"
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
                    rows={8}
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500 font-mono text-sm resize-none"
                  />
                </div>

                <div className="flex justify-end space-x-3 mt-6">
                  <button
                    type="button"
                    onClick={() => setShowAddResourceModal(false)}
                    className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={!newResource.name.trim() || !newResource.content.trim() || resourceOperationPending}
                    className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
                  >
                    {resourceOperationPending ? 'Adding...' : 'Add Resource'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Import Resource Modal */}
        {showImportModal && (() => {
          // Filter out resources already imported to this workflow
          const importedSourceIds = new Set(
            resources.filter(r => r.source_id).map(r => r.source_id)
          )
          const availableResources = projectResources.filter(
            pr => !importedSourceIds.has(pr.id)
          )

          return (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
            <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 w-full max-w-lg mx-4">
              <h3 className="text-lg font-semibold text-white mb-4">Import from Project Library</h3>
              <p className="text-sm text-gray-400 mb-4">
                Select a resource from the project's shared library.
              </p>

              {availableResources.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-gray-400">
                    {projectResources.length === 0
                      ? 'No shared resources in project library'
                      : 'All project resources are already imported'}
                  </p>
                </div>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {availableResources.map((pr) => (
                    <button
                      key={pr.id}
                      onClick={() => handleImportResource(pr)}
                      disabled={resourceOperationPending}
                      className="w-full p-3 bg-gray-700 rounded-lg hover:bg-gray-600 text-left disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <div className="flex items-center justify-between">
                        <div>
                          <h4 className="text-white font-medium">{pr.name}</h4>
                          <p className="text-sm text-gray-400">{getResourceTypeLabel(pr.resource_type)}</p>
                        </div>
                        {pr.auto_inherit && (
                          <span className="text-xs bg-primary-500/20 text-primary-400 px-2 py-1 rounded">
                            Auto
                          </span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}

              <div className="flex justify-end mt-4">
                <button
                  onClick={() => setShowImportModal(false)}
                  className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
          )
        })()}

        {/* Edit Resource Modal */}
        {editingResource && (
          <div className="absolute inset-0 bg-black/50 flex items-center justify-center">
            <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 w-full max-w-2xl mx-4 max-h-[80vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-white">{editingResource.name}</h3>
                <span className="text-sm bg-gray-700 text-gray-400 px-2 py-1 rounded">
                  {getResourceTypeLabel(editingResource.resource_type)}
                </span>
              </div>

              <textarea
                value={editResourceContent}
                onChange={(e) => setEditResourceContent(e.target.value)}
                rows={16}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white font-mono text-sm resize-none"
              />

              <div className="flex justify-end space-x-3 mt-4">
                <button
                  onClick={() => setEditingResource(null)}
                  className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveResourceEdit}
                  disabled={resourceOperationPending}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
                >
                  {resourceOperationPending ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Permission Editor Modal */}
        {showPermissionEditor && permissionEditLoopName && (
          <LoopPermissionEditor
            projectSlug={projectSlug}
            loopName={permissionEditLoopName}
            onClose={() => {
              setShowPermissionEditor(false)
              setPermissionEditLoopName(null)
            }}
            onSave={() => {
              // Permissions saved successfully
            }}
          />
        )}
      </div>
    </div>
  )
}
