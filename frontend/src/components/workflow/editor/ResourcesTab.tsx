import { useState, useEffect } from 'react'
import type { WorkflowResource, ProjectResource } from '../../../api'
import {
  createWorkflowResource,
  updateWorkflowResource,
  deleteWorkflowResource,
  importProjectResourceToWorkflow,
} from '../../../api'

interface ResourcesTabProps {
  projectSlug: string
  workflowId: string
  resources: WorkflowResource[]
  projectResources: ProjectResource[]
  onResourcesChange: () => void
  onError: (error: string) => void
}

export default function ResourcesTab({
  projectSlug,
  workflowId,
  resources,
  projectResources,
  onResourcesChange,
  onError,
}: ResourcesTabProps) {
  const [operationPending, setOperationPending] = useState(false)
  const [showAddModal, setShowAddModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [editingResource, setEditingResource] = useState<WorkflowResource | null>(null)
  const [editContent, setEditContent] = useState('')
  const [newResource, setNewResource] = useState({
    name: '',
    resource_type: 'guardrail',
    content: '',
  })

  // Handle Escape key to close modals
  useEffect(() => {
    const hasOpenModal = showAddModal || showImportModal || editingResource !== null
    if (!hasOpenModal) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (showAddModal) {
          setShowAddModal(false)
          setNewResource({ name: '', resource_type: 'guardrail', content: '' })
        } else if (showImportModal) {
          setShowImportModal(false)
        } else if (editingResource) {
          setEditingResource(null)
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showAddModal, showImportModal, editingResource])

  const handleAddResource = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newResource.name.trim() || !newResource.content.trim()) return
    if (operationPending) return

    setOperationPending(true)
    try {
      await createWorkflowResource(projectSlug, workflowId, {
        name: newResource.name.trim(),
        resource_type: newResource.resource_type,
        content: newResource.content.trim(),
        source: 'manual',
      })
      setNewResource({ name: '', resource_type: 'guardrail', content: '' })
      setShowAddModal(false)
      onResourcesChange()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to add resource')
    } finally {
      setOperationPending(false)
    }
  }

  const handleImportResource = async (projectResource: ProjectResource) => {
    if (operationPending) return

    setOperationPending(true)
    try {
      await importProjectResourceToWorkflow(projectSlug, workflowId, projectResource.id)
      setShowImportModal(false)
      onResourcesChange()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to import resource')
    } finally {
      setOperationPending(false)
    }
  }

  const handleToggleResource = async (resource: WorkflowResource) => {
    if (operationPending) return

    setOperationPending(true)
    try {
      await updateWorkflowResource(projectSlug, workflowId, resource.id, {
        enabled: !resource.enabled,
      })
      onResourcesChange()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to update resource')
    } finally {
      setOperationPending(false)
    }
  }

  const handleSaveEdit = async () => {
    if (!editingResource) return
    if (operationPending) return

    setOperationPending(true)
    try {
      await updateWorkflowResource(projectSlug, workflowId, editingResource.id, {
        content: editContent,
      })
      setEditingResource(null)
      onResourcesChange()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to save resource')
    } finally {
      setOperationPending(false)
    }
  }

  const handleDeleteResource = async (resource: WorkflowResource) => {
    if (!confirm(`Delete "${resource.name}"? This cannot be undone.`)) return
    if (operationPending) return

    setOperationPending(true)
    try {
      await deleteWorkflowResource(projectSlug, workflowId, resource.id)
      onResourcesChange()
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to delete resource')
    } finally {
      setOperationPending(false)
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

  // Filter out already imported resources
  const importedSourceIds = new Set(
    resources.filter(r => r.source_id).map(r => r.source_id)
  )
  const availableForImport = projectResources.filter(
    pr => !importedSourceIds.has(pr.id)
  )

  // Group resources by type
  const designDocs = resources.filter(r => r.resource_type === 'design_doc')
  const guidelines = resources.filter(r => r.resource_type === 'guardrail')
  const inputFiles = resources.filter(r => r.resource_type === 'input_file')
  const prompts = resources.filter(r => r.resource_type === 'prompt')
  const other = resources.filter(r => !['design_doc', 'guardrail', 'input_file', 'prompt'].includes(r.resource_type))

  const renderResourceSection = (title: string, items: WorkflowResource[], icon: React.ReactNode) => {
    if (items.length === 0) return null
    return (
      <div className="space-y-3">
        <h3 className="flex items-center gap-2 text-sm font-medium text-gray-300">
          {icon}
          {title}
          <span className="text-gray-500">({items.length})</span>
        </h3>
        <div className="space-y-2">
          {items.map((resource) => (
            <div
              key={resource.id}
              className="flex items-start space-x-3 p-4 bg-gray-800 rounded-lg border border-gray-700"
            >
              <div className={`p-2 rounded ${resource.enabled ? 'bg-primary-500/20 text-primary-400' : 'bg-gray-700 text-gray-500'}`}>
                {getResourceTypeIcon(resource.resource_type)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium text-white truncate">{resource.name}</div>
                <div className="text-xs text-gray-400">
                  {getResourceTypeLabel(resource.resource_type)}
                  {resource.source && ` • ${resource.source}`}
                </div>
                {resource.content && (
                  <p className="text-xs text-gray-500 mt-1 line-clamp-2">
                    {resource.content.length > 150
                      ? `${resource.content.slice(0, 150)}...`
                      : resource.content}
                  </p>
                )}
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleToggleResource(resource)}
                  disabled={operationPending}
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
                    setEditContent(resource.content || '')
                  }}
                  disabled={operationPending}
                  className="p-1 text-gray-400 hover:text-white disabled:opacity-50"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                </button>
                <button
                  onClick={() => handleDeleteResource(resource)}
                  disabled={operationPending}
                  className="p-1 text-gray-400 hover:text-red-400 disabled:opacity-50"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-4xl">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-white">Workflow Resources</h2>
          <p className="text-sm text-gray-400 mt-1">
            These resources are available to all steps in this workflow
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center space-x-1 px-3 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            <span>Import from Library</span>
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center space-x-1 px-3 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Add Resource</span>
          </button>
        </div>
      </div>

      {/* Resources List */}
      {resources.length === 0 ? (
        <div className="text-center py-12 card">
          <svg className="w-16 h-16 mx-auto text-gray-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3 className="text-lg font-medium text-gray-300 mb-2">No Resources Yet</h3>
          <p className="text-gray-500 mb-4 max-w-md mx-auto">
            Add design documents, guidelines, or other context to help Claude understand your project.
          </p>
          <div className="flex items-center justify-center space-x-3">
            <button
              onClick={() => setShowImportModal(true)}
              className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
            >
              Import from Library
            </button>
            <button
              onClick={() => setShowAddModal(true)}
              className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500"
            >
              Add Resource
            </button>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {renderResourceSection('Design Documents', designDocs, (
            <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          ))}
          {renderResourceSection('Guidelines', guidelines, (
            <svg className="w-4 h-4 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          ))}
          {renderResourceSection('Input Files', inputFiles, (
            <svg className="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
          ))}
          {renderResourceSection('Prompts', prompts, (
            <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
          ))}
          {renderResourceSection('Other', other, (
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h7" />
            </svg>
          ))}
        </div>
      )}

      {/* Add Resource Modal */}
      {showAddModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowAddModal(false)
              setNewResource({ name: '', resource_type: 'guardrail', content: '' })
            }
          }}
        >
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
                  <option value="design_doc">Design Document</option>
                  <option value="guardrail">Guideline</option>
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

              {/* File Upload */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Upload File <span className="text-gray-500 font-normal">(optional)</span>
                </label>
                <div className="flex items-center gap-2">
                  <label className="flex-1 flex items-center justify-center gap-2 px-4 py-3 bg-gray-700 border border-gray-600 border-dashed rounded-lg cursor-pointer hover:bg-gray-650 hover:border-gray-500 transition-colors">
                    <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                    <span className="text-sm text-gray-400">
                      Click to upload .md, .txt, or .json
                    </span>
                    <input
                      type="file"
                      accept=".md,.txt,.json,.markdown"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0]
                        if (file) {
                          // Auto-fill name from filename if empty
                          if (!newResource.name.trim()) {
                            const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '')
                            setNewResource(prev => ({ ...prev, name: nameWithoutExt }))
                          }
                          // Read file content
                          const reader = new FileReader()
                          reader.onload = (event) => {
                            const content = event.target?.result as string
                            setNewResource(prev => ({ ...prev, content }))
                          }
                          reader.readAsText(file)
                        }
                        // Reset input so same file can be selected again
                        e.target.value = ''
                      }}
                    />
                  </label>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Content
                </label>
                <textarea
                  value={newResource.content}
                  onChange={(e) => setNewResource({ ...newResource, content: e.target.value })}
                  placeholder="Paste content here or upload a file above..."
                  rows={10}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500 font-mono text-sm resize-none"
                />
                {newResource.content && (
                  <p className="text-xs text-gray-500 mt-1">
                    {newResource.content.length.toLocaleString()} characters
                  </p>
                )}
              </div>

              <div className="flex justify-end space-x-3 mt-6">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddModal(false)
                    setNewResource({ name: '', resource_type: 'guardrail', content: '' })
                  }}
                  className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!newResource.name.trim() || !newResource.content.trim() || operationPending}
                  className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
                >
                  {operationPending ? 'Adding...' : 'Add Resource'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setShowImportModal(false)
          }}
        >
          <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 w-full max-w-lg mx-4">
            <h3 className="text-lg font-semibold text-white mb-4">Import from Project Library</h3>
            <p className="text-sm text-gray-400 mb-4">
              Select a resource from the project's shared library.
            </p>

            {availableForImport.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-400">
                  {projectResources.length === 0
                    ? 'No shared resources in project library'
                    : 'All project resources are already imported'}
                </p>
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {availableForImport.map((pr) => (
                  <button
                    key={pr.id}
                    onClick={() => handleImportResource(pr)}
                    disabled={operationPending}
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
      )}

      {/* Edit Resource Modal */}
      {editingResource && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) setEditingResource(null)
          }}
        >
          <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 w-full max-w-2xl mx-4 max-h-[80vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">{editingResource.name}</h3>
              <span className="text-sm bg-gray-700 text-gray-400 px-2 py-1 rounded">
                {getResourceTypeLabel(editingResource.resource_type)}
              </span>
            </div>

            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
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
                onClick={handleSaveEdit}
                disabled={operationPending}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
              >
                {operationPending ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
