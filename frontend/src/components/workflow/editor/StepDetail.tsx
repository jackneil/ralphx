import { useState, useEffect, useCallback } from 'react'
import type { WorkflowStep, WorkflowResource, StepResource, PreviewPromptResponse } from '../../../api'
import ConfirmDialog from '../../ConfirmDialog'
import {
  listWorkflowResources,
  listStepResources,
  createStepResource,
  deleteStepResource,
  disableInheritedResource,
  enableInheritedResource,
  previewStepPrompt,
} from '../../../api'
import StepSettings from './StepSettings'
import LoopPermissionEditor from '../../LoopPermissionEditor'

type StepDetailTab = 'settings' | 'resources' | 'permissions'

interface StepDetailProps {
  projectSlug: string
  workflowId: string
  step: WorkflowStep
  onChange: (step: WorkflowStep) => void
  onClone: () => void
  onArchive: () => void
  onError: (error: string) => void
}

export default function StepDetail({
  projectSlug,
  workflowId,
  step,
  onChange,
  onClone,
  onArchive,
  onError,
}: StepDetailProps) {
  const [activeTab, setActiveTab] = useState<StepDetailTab>('settings')

  // Resources state
  const [workflowResources, setWorkflowResources] = useState<WorkflowResource[]>([])
  const [stepResources, setStepResources] = useState<StepResource[]>([])
  const [resourcesLoading, setResourcesLoading] = useState(false)
  const [resourceOperationPending, setResourceOperationPending] = useState(false)
  const [showAddResourceModal, setShowAddResourceModal] = useState(false)
  const [newResource, setNewResource] = useState({
    name: '',
    resource_type: 'guardrail',
    content: '',
  })

  // Prompt preview state
  const [showPreviewModal, setShowPreviewModal] = useState(false)
  const [previewData, setPreviewData] = useState<PreviewPromptResponse | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  // Permission editor state
  const [showPermissionEditor, setShowPermissionEditor] = useState(false)

  // Archive confirmation state
  const [showArchiveConfirm, setShowArchiveConfirm] = useState(false)

  // Reset tab when step changes
  useEffect(() => {
    setActiveTab('settings')
  }, [step.id])

  // Handle Escape key to close modals
  useEffect(() => {
    const hasOpenModal = showAddResourceModal || showPreviewModal || showPermissionEditor
    if (!hasOpenModal) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showAddResourceModal) setShowAddResourceModal(false)
        else if (showPreviewModal) setShowPreviewModal(false)
        else if (showPermissionEditor) setShowPermissionEditor(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showAddResourceModal, showPreviewModal, showPermissionEditor])

  // Load resources when resources tab is selected
  const loadResources = useCallback(async () => {
    if (!step.id) return
    setResourcesLoading(true)
    try {
      const [wfRes, stepRes] = await Promise.all([
        listWorkflowResources(projectSlug, workflowId),
        listStepResources(projectSlug, workflowId, step.id),
      ])
      setWorkflowResources(wfRes)
      setStepResources(stepRes)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load resources')
    } finally {
      setResourcesLoading(false)
    }
  }, [projectSlug, workflowId, step.id, onError])

  useEffect(() => {
    if (activeTab === 'resources' && step.id) {
      loadResources()
    }
  }, [activeTab, step.id, loadResources])

  const handleToggleInheritedResource = async (workflowResource: WorkflowResource) => {
    if (!step.id || resourceOperationPending) return

    setResourceOperationPending(true)
    try {
      const existingDisable = stepResources.find(
        sr => sr.workflow_resource_id === workflowResource.id && sr.mode === 'disable'
      )

      if (existingDisable) {
        await enableInheritedResource(projectSlug, workflowId, step.id, workflowResource.id)
      } else {
        await disableInheritedResource(projectSlug, workflowId, step.id, workflowResource.id)
      }
      await loadResources()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to toggle resource')
    } finally {
      setResourceOperationPending(false)
    }
  }

  const isResourceDisabled = (workflowResourceId: number): boolean => {
    return stepResources.some(
      sr => sr.workflow_resource_id === workflowResourceId && sr.mode === 'disable'
    )
  }

  const handleAddStepResource = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!step.id || !newResource.name.trim() || !newResource.content.trim()) return
    if (resourceOperationPending) return

    setResourceOperationPending(true)
    try {
      await createStepResource(projectSlug, workflowId, step.id, {
        mode: 'add',
        resource_type: newResource.resource_type,
        name: newResource.name.trim(),
        content: newResource.content.trim(),
      })
      setNewResource({ name: '', resource_type: 'guardrail', content: '' })
      setShowAddResourceModal(false)
      await loadResources()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to add step resource')
    } finally {
      setResourceOperationPending(false)
    }
  }

  const handleDeleteStepResource = async (resource: StepResource) => {
    if (!step.id || resourceOperationPending) return
    if (!confirm('Delete this step resource?')) return

    setResourceOperationPending(true)
    try {
      await deleteStepResource(projectSlug, workflowId, step.id, resource.id)
      await loadResources()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to delete step resource')
    } finally {
      setResourceOperationPending(false)
    }
  }

  const handlePreviewPrompt = async () => {
    if (!step.id) return

    setPreviewLoading(true)
    try {
      const preview = await previewStepPrompt(projectSlug, workflowId, step.id)
      setPreviewData(preview)
      setShowPreviewModal(true)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to load preview')
    } finally {
      setPreviewLoading(false)
    }
  }

  const getResourceTypeLabel = (type: string) => {
    switch (type) {
      case 'design_doc': return 'Design Document'
      case 'guardrail': return 'Guideline'
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

  const tabs: { key: StepDetailTab; label: string; disabled?: boolean }[] = [
    { key: 'settings', label: 'Settings' },
    { key: 'resources', label: 'Resources', disabled: !step.id || step.step_type !== 'autonomous' },
    { key: 'permissions', label: 'Permissions', disabled: !step.id || step.step_type !== 'autonomous' },
  ]

  return (
    <div className="card h-full flex flex-col">
      {/* Step Header */}
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-700">
        <div>
          <h2 className="text-lg font-semibold text-white">
            Step {step.step_number}: {step.name || 'Untitled'}
          </h2>
          <p className="text-sm text-gray-400 mt-1">
            {step.step_type === 'interactive' ? 'Chat Step' : 'Automated Step'}
            {step.config?.model && step.step_type === 'autonomous' && ` (${step.config.model})`}
          </p>
        </div>

        <div className="flex items-center gap-2">
          {!step.id && (
            <span className="px-2 py-1 text-xs rounded bg-yellow-900/50 text-yellow-400 border border-yellow-700/50">
              Save workflow to enable all features
            </span>
          )}
          <button
            onClick={onClone}
            className="px-3 py-1.5 text-sm text-gray-400 hover:text-white bg-gray-700 hover:bg-gray-600 rounded transition-colors"
            title="Clone step"
          >
            Clone
          </button>
          <button
            onClick={() => setShowArchiveConfirm(true)}
            className="px-3 py-1.5 text-sm text-red-400 hover:text-red-300 bg-gray-700 hover:bg-red-900/30 rounded transition-colors"
            title="Archive step"
          >
            Archive
          </button>
        </div>
      </div>

      {/* Sub-tabs (only for autonomous steps) */}
      {step.step_type === 'autonomous' && (
        <div className="flex space-x-1 border-b border-gray-700 mb-4">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => !tab.disabled && setActiveTab(tab.key)}
              disabled={tab.disabled}
              className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === tab.key
                  ? 'border-primary-500 text-white'
                  : tab.disabled
                    ? 'border-transparent text-gray-600 cursor-not-allowed'
                    : 'border-transparent text-gray-400 hover:text-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto">
        {/* Settings Tab */}
        {(activeTab === 'settings' || step.step_type === 'interactive') && (
          <StepSettings
            step={step}
            onChange={onChange}
          />
        )}

        {/* Resources Tab */}
        {activeTab === 'resources' && step.step_type === 'autonomous' && step.id && (
          <div className="space-y-6">
            {/* Inherited Resources */}
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

              {resourcesLoading ? (
                <div className="text-center py-4 text-gray-500">Loading resources...</div>
              ) : workflowResources.length === 0 ? (
                <div className="text-center py-4 text-gray-500">
                  No workflow resources. Add resources in the Resources tab.
                </div>
              ) : (
                <div className="space-y-2">
                  {workflowResources.map((wr) => {
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
                          disabled={resourceOperationPending}
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
                  onClick={() => setShowAddResourceModal(true)}
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
                        disabled={resourceOperationPending}
                        className="p-1 text-gray-400 hover:text-red-400 disabled:opacity-50"
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

        {/* Permissions Tab */}
        {activeTab === 'permissions' && step.step_type === 'autonomous' && step.id && (
          <div>
            {step.loop_name ? (
              <div className="space-y-4">
                <p className="text-sm text-gray-400">
                  Configure which tools and file operations Claude can use during this step's execution.
                </p>
                <button
                  type="button"
                  onClick={() => setShowPermissionEditor(true)}
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
                  <p className="text-sm text-gray-300">Permissions can be configured after the step is started for the first time.</p>
                  <p className="mt-1 text-xs text-gray-500">
                    Start the workflow to create the execution environment, then return here to configure permissions.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add Step Resource Modal */}
      {showAddResourceModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowAddResourceModal(false)
          }}
        >
          <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 w-full max-w-lg mx-4 max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-semibold text-white mb-4">Add Step Resource</h3>

            <form onSubmit={handleAddStepResource} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Resource Type
                </label>
                <select
                  value={newResource.resource_type}
                  onChange={(e) => setNewResource({ ...newResource, resource_type: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                >
                  <option value="guardrail">Guideline</option>
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
                  placeholder="e.g., Step-Specific Guidelines"
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

      {/* Preview Prompt Modal */}
      {showPreviewModal && previewData && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowPreviewModal(false)
          }}
        >
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

      {/* Permission Editor Modal */}
      {showPermissionEditor && step.loop_name && (
        <LoopPermissionEditor
          projectSlug={projectSlug}
          loopName={step.loop_name}
          onClose={() => setShowPermissionEditor(false)}
          onSave={() => {}}
        />
      )}

      {/* Archive Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showArchiveConfirm}
        title={`Archive "${step.name}"?`}
        message="This step will be moved to the trash and can be recovered later."
        details={
          (step.iterations_completed || 0) > 0 || (step.items_generated || 0) > 0
            ? `This step has ${step.iterations_completed || 0} iterations and ${step.items_generated || 0} items generated. These will be preserved.`
            : undefined
        }
        confirmLabel="Archive Step"
        variant="danger"
        onConfirm={() => {
          setShowArchiveConfirm(false)
          onArchive()
        }}
        onCancel={() => setShowArchiveConfirm(false)}
      />
    </div>
  )
}
