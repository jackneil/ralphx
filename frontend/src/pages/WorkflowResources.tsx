import { useEffect, useState, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getProject,
  getWorkflow,
  listWorkflowResources,
  createWorkflowResource,
  updateWorkflowResource,
  deleteWorkflowResource,
  listProjectResources,
  importProjectResourceToWorkflow,
  WorkflowResource,
  ProjectResource,
  Workflow,
} from '../api'
import { useDashboardStore } from '../stores/dashboard'

type ResourceTab = 'design_doc' | 'guardrail' | 'input_file' | 'all'

export default function WorkflowResources() {
  const { slug, workflowId } = useParams<{ slug: string; workflowId: string }>()
  const { selectedProject, setSelectedProject } = useDashboardStore()

  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [resources, setResources] = useState<WorkflowResource[]>([])
  const [projectResources, setProjectResources] = useState<ProjectResource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Current tab
  const [activeTab, setActiveTab] = useState<ResourceTab>('all')

  // Add resource modal
  const [showAddModal, setShowAddModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [newResource, setNewResource] = useState({
    name: '',
    resource_type: 'guardrail',
    content: '',
  })
  const [adding, setAdding] = useState(false)

  // View/Edit modal
  const [selectedResource, setSelectedResource] = useState<WorkflowResource | null>(null)
  const [editContent, setEditContent] = useState('')
  const [saving, setSaving] = useState(false)

  const loadData = useCallback(async () => {
    if (!slug || !workflowId) return
    setLoading(true)
    setError(null)

    try {
      const [projectData, workflowData, resourcesData, projectResourcesData] = await Promise.all([
        getProject(slug),
        getWorkflow(slug, workflowId),
        listWorkflowResources(slug, workflowId),
        listProjectResources(slug),
      ])
      setSelectedProject(projectData)
      setWorkflow(workflowData)
      setResources(resourcesData)
      setProjectResources(projectResourcesData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load resources')
    } finally {
      setLoading(false)
    }
  }, [slug, workflowId, setSelectedProject])

  useEffect(() => {
    loadData()
  }, [loadData])

  const filteredResources = activeTab === 'all'
    ? resources
    : resources.filter(r => r.resource_type === activeTab)

  const handleAddResource = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!slug || !workflowId || !newResource.name.trim() || !newResource.content.trim()) return

    setAdding(true)
    try {
      await createWorkflowResource(slug, workflowId, {
        name: newResource.name.trim(),
        resource_type: newResource.resource_type,
        content: newResource.content.trim(),
        source: 'manual',
      })
      setNewResource({ name: '', resource_type: 'guardrail', content: '' })
      setShowAddModal(false)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add resource')
    } finally {
      setAdding(false)
    }
  }

  const handleImport = async (projectResource: ProjectResource) => {
    if (!slug || !workflowId) return

    try {
      await importProjectResourceToWorkflow(slug, workflowId, projectResource.id)
      setShowImportModal(false)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import resource')
    }
  }

  const handleSaveEdit = async () => {
    if (!slug || !workflowId || !selectedResource) return

    setSaving(true)
    try {
      await updateWorkflowResource(slug, workflowId, selectedResource.id, {
        content: editContent,
      })
      setSelectedResource(null)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save resource')
    } finally {
      setSaving(false)
    }
  }

  const handleToggleEnabled = async (resource: WorkflowResource) => {
    if (!slug || !workflowId) return

    try {
      await updateWorkflowResource(slug, workflowId, resource.id, {
        enabled: !resource.enabled,
      })
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update resource')
    }
  }

  const handleDelete = async (resource: WorkflowResource) => {
    if (!slug || !workflowId) return
    if (!confirm(`Delete "${resource.name}"? This cannot be undone.`)) return

    try {
      await deleteWorkflowResource(slug, workflowId, resource.id)
      loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete resource')
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

  const tabs: { key: ResourceTab; label: string }[] = [
    { key: 'all', label: 'All' },
    { key: 'design_doc', label: 'Design Doc' },
    { key: 'guardrail', label: 'Guardrails' },
    { key: 'input_file', label: 'Input Files' },
  ]

  if (loading) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading resources...</div>
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
        <Link to={`/projects/${slug}/workflows/${workflowId}`} className="hover:text-white">
          {workflow?.name || 'Workflow'}
        </Link>
        <span>/</span>
        <span className="text-white">Resources</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white mb-1">Resources</h1>
          <p className="text-gray-400">
            {resources.length} resource{resources.length !== 1 ? 's' : ''} for this workflow
          </p>
        </div>
        <div className="flex space-x-3">
          <button
            onClick={() => setShowImportModal(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            <span>Import from Library</span>
          </button>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Add Resource</span>
          </button>
        </div>
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
            onClick={() => setActiveTab(tab.key)}
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

      {/* Resources List */}
      {filteredResources.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-gray-400">No resources found</p>
          <p className="text-sm text-gray-500 mt-2">
            Add resources to provide context for Claude during execution.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredResources.map(resource => (
            <div
              key={resource.id}
              className="card flex items-start justify-between"
            >
              <div className="flex items-start space-x-4">
                <div className={`p-2 rounded ${resource.enabled ? 'bg-primary-500/20 text-primary-400' : 'bg-gray-700 text-gray-500'}`}>
                  {getResourceTypeIcon(resource.resource_type)}
                </div>
                <div>
                  <h3 className="text-lg font-medium text-white">{resource.name}</h3>
                  <div className="flex items-center space-x-4 text-sm text-gray-400 mt-1">
                    <span>{getResourceTypeLabel(resource.resource_type)}</span>
                    {resource.source && (
                      <>
                        <span className="text-gray-600">|</span>
                        <span>Source: {resource.source}</span>
                      </>
                    )}
                  </div>
                  {resource.content && (
                    <p className="text-sm text-gray-500 mt-2 line-clamp-2">
                      {resource.content.slice(0, 200)}
                      {resource.content.length > 200 && '...'}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => handleToggleEnabled(resource)}
                  className={`px-3 py-1 text-sm rounded ${
                    resource.enabled
                      ? 'bg-green-600/20 text-green-400'
                      : 'bg-gray-700 text-gray-500'
                  }`}
                >
                  {resource.enabled ? 'Enabled' : 'Disabled'}
                </button>
                <button
                  onClick={() => {
                    setSelectedResource(resource)
                    setEditContent(resource.content || '')
                  }}
                  className="px-3 py-1 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
                >
                  View
                </button>
                <button
                  onClick={() => handleDelete(resource)}
                  className="px-3 py-1 text-sm rounded bg-red-900/30 text-red-400 hover:bg-red-900/50"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Help Text */}
      <div className="mt-8 p-4 bg-gray-800/50 border border-gray-700 rounded">
        <div className="flex items-start space-x-3">
          <svg className="w-5 h-5 text-yellow-500 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="text-sm text-gray-400">
            <p className="font-medium text-gray-300 mb-1">About Workflow Resources</p>
            <p>
              Resources are injected into Claude's context during execution.
              Design documents provide the overall vision, guardrails set boundaries,
              and input files provide additional context.
            </p>
          </div>
        </div>
      </div>

      {/* Add Resource Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
            <h2 className="text-xl font-bold text-white mb-4">Add Resource</h2>
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

      {/* Import from Library Modal */}
      {showImportModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-lg">
            <h2 className="text-xl font-bold text-white mb-4">Import from Project Library</h2>
            <p className="text-sm text-gray-400 mb-4">
              Select a resource from the project's shared library to add to this workflow.
            </p>
            {projectResources.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-400">No shared resources in project library</p>
                <p className="text-sm text-gray-500 mt-2">
                  Add resources to the project library in Project Settings.
                </p>
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {projectResources.map(pr => (
                  <button
                    key={pr.id}
                    onClick={() => handleImport(pr)}
                    className="w-full p-3 bg-gray-700 rounded hover:bg-gray-600 text-left"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="text-white font-medium">{pr.name}</h4>
                        <p className="text-sm text-gray-400">{getResourceTypeLabel(pr.resource_type)}</p>
                      </div>
                      {pr.auto_inherit && (
                        <span className="text-xs bg-primary-500/20 text-primary-400 px-2 py-1 rounded">
                          Auto-inherit
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
                className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* View/Edit Modal */}
      {selectedResource && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-4xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-white">{selectedResource.name}</h2>
              <span className="text-sm bg-gray-700 text-gray-400 px-2 py-1 rounded">
                {getResourceTypeLabel(selectedResource.resource_type)}
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
                onClick={() => setSelectedResource(null)}
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
