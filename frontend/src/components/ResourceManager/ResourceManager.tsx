import { useState, useEffect, useCallback } from 'react'
import {
  listResources,
  createResource,
  updateResource,
  deleteResource,
  syncResources,
  Resource,
} from '../../api'
import ProjectFileBrowser from './ProjectFileBrowser'

interface ResourceManagerProps {
  projectSlug: string
}

const RESOURCE_TYPES = [
  { value: 'loop_template', label: 'Loop Template', description: 'Base loop instructions (main driving prompt)' },
  { value: 'design_doc', label: 'Design Document', description: 'Project design and requirements' },
  { value: 'architecture', label: 'Architecture', description: 'System architecture docs' },
  { value: 'coding_standards', label: 'Coding Standards', description: 'Coding guidelines and rules' },
  { value: 'domain_knowledge', label: 'Domain Knowledge', description: 'Domain-specific context' },
  { value: 'guardrails', label: 'Guardrails', description: 'Quality rules and constraints' },
  { value: 'custom', label: 'Custom', description: 'Other resources' },
]

const INJECTION_POSITIONS = [
  { value: 'template_body', label: 'Template Body', description: 'The base template itself' },
  { value: 'before_prompt', label: 'Before Prompt', description: 'At the very start' },
  { value: 'after_design_doc', label: 'After Design Doc', description: 'After design context' },
  { value: 'before_task', label: 'Before Task', description: 'Before task instructions' },
  { value: 'after_task', label: 'After Task', description: 'At the end' },
]

export default function ResourceManager({ projectSlug }: ResourceManagerProps) {
  const [resources, setResources] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Selected resource for editing
  const [selectedResource, setSelectedResource] = useState<Resource | null>(null)
  const [editContent, setEditContent] = useState('')

  // Create dialog
  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({
    name: '',
    resource_type: 'design_doc',
    content: '',
  })

  // Sync status
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<{ added: number; updated: number; removed: number } | null>(null)

  // File browser dialog
  const [showFileBrowser, setShowFileBrowser] = useState(false)

  // Load resources
  const loadResources = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await listResources(projectSlug, { include_content: false })
      setResources(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load resources')
    } finally {
      setLoading(false)
    }
  }, [projectSlug])

  useEffect(() => {
    loadResources()
  }, [loadResources])

  // Select resource for editing
  const handleSelect = async (resource: Resource) => {
    try {
      const fullResource = await listResources(projectSlug, { include_content: true })
      const found = fullResource.find((r) => r.id === resource.id)
      if (found) {
        setSelectedResource(found)
        setEditContent(found.content || '')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load resource')
    }
  }

  // Save edits
  const handleSaveEdit = async () => {
    if (!selectedResource) return

    try {
      await updateResource(projectSlug, selectedResource.id, {
        content: editContent,
      })
      await loadResources()
      setSelectedResource(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    }
  }

  // Toggle enabled
  const handleToggleEnabled = async (resource: Resource) => {
    try {
      await updateResource(projectSlug, resource.id, {
        enabled: !resource.enabled,
      })
      await loadResources()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update')
    }
  }

  // Toggle inherit default
  const handleToggleInherit = async (resource: Resource) => {
    try {
      await updateResource(projectSlug, resource.id, {
        inherit_default: !resource.inherit_default,
      })
      await loadResources()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update')
    }
  }

  // Delete resource
  const handleDelete = async (resource: Resource) => {
    if (!window.confirm(`Delete "${resource.name}"? This will also delete the file.`)) {
      return
    }

    try {
      await deleteResource(projectSlug, resource.id)
      await loadResources()
      if (selectedResource?.id === resource.id) {
        setSelectedResource(null)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete')
    }
  }

  // Create resource
  const handleCreate = async () => {
    if (!createForm.name.trim() || !createForm.content.trim()) {
      setError('Name and content are required')
      return
    }

    try {
      await createResource(projectSlug, {
        name: createForm.name,
        resource_type: createForm.resource_type,
        content: createForm.content,
      })
      await loadResources()
      setShowCreate(false)
      setCreateForm({ name: '', resource_type: 'design_doc', content: '' })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create')
    }
  }

  // Sync from filesystem
  const handleSync = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const result = await syncResources(projectSlug)
      setSyncResult(result)
      await loadResources()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to sync')
    } finally {
      setSyncing(false)
    }
  }

  // Handle file selection from project browser
  const handleFileSelect = (file: { path: string; content: string; filename: string }) => {
    setShowFileBrowser(false)

    // Extract name from filename (without extension)
    const name = file.filename.replace(/\.[^/.]+$/, '')

    // Infer resource type from path or default to custom
    let resourceType = 'custom'
    const pathLower = file.path.toLowerCase()
    if (pathLower.includes('design') || pathLower.includes('spec') || pathLower.includes('requirement')) {
      resourceType = 'design_doc'
    } else if (pathLower.includes('arch') || pathLower.includes('system')) {
      resourceType = 'architecture'
    } else if (pathLower.includes('standard') || pathLower.includes('style') || pathLower.includes('guideline')) {
      resourceType = 'coding_standards'
    } else if (pathLower.includes('domain') || pathLower.includes('context') || pathLower.includes('knowledge')) {
      resourceType = 'domain_knowledge'
    }

    // Pre-fill create form and open dialog
    setCreateForm({
      name,
      resource_type: resourceType,
      content: file.content,
    })
    setShowCreate(true)
  }

  // Group resources by type
  const groupedResources = RESOURCE_TYPES.map((type) => ({
    type,
    resources: resources.filter((r) => r.resource_type === type.value),
  })).filter((g) => g.resources.length > 0)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">Project Resources</h3>
          <p className="text-sm text-gray-400">
            Resources are automatically injected into loop prompts based on type
          </p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={handleSync}
            disabled={syncing}
            className="px-3 py-1.5 text-sm bg-gray-700 text-white rounded hover:bg-gray-600 disabled:opacity-50"
          >
            {syncing ? 'Syncing...' : 'Sync from Files'}
          </button>
          <button
            onClick={() => setShowFileBrowser(true)}
            className="px-3 py-1.5 text-sm bg-gray-700 text-white rounded hover:bg-gray-600"
          >
            Import from Project
          </button>
          <button
            onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded hover:bg-primary-500"
          >
            Add Resource
          </button>
        </div>
      </div>

      {/* Sync Result */}
      {syncResult && (
        <div className="p-3 bg-green-900/30 border border-green-800 rounded text-sm text-green-400">
          Synced: {syncResult.added} added, {syncResult.updated} updated, {syncResult.removed} removed
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">Dismiss</button>
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="flex items-center justify-center p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500" />
        </div>
      ) : resources.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          <p>No resources yet.</p>
          <p className="text-sm mt-1">
            Add resources to <code>.ralphx/resources/</code> directories and sync,<br />
            or click "Add Resource" to create one.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {groupedResources.map(({ type, resources: typeResources }) => (
            <div key={type.value} className="bg-gray-800/50 rounded-lg p-4">
              <h4 className="text-sm font-medium text-gray-300 mb-3">
                {type.label}
                <span className="ml-2 text-gray-500 font-normal">({typeResources.length})</span>
              </h4>
              <div className="space-y-2">
                {typeResources.map((resource) => (
                  <ResourceRow
                    key={resource.id}
                    resource={resource}
                    onSelect={() => handleSelect(resource)}
                    onToggleEnabled={() => handleToggleEnabled(resource)}
                    onToggleInherit={() => handleToggleInherit(resource)}
                    onDelete={() => handleDelete(resource)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Edit Dialog */}
      {selectedResource && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg w-full max-w-3xl max-h-[90vh] flex flex-col">
            <div className="p-4 border-b border-gray-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Edit: {selectedResource.name}</h3>
              <button
                onClick={() => setSelectedResource(null)}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 p-4 overflow-y-auto">
              <div className="mb-4 text-sm text-gray-400">
                <span>Type: {selectedResource.resource_type.replace('_', ' ')}</span>
                <span className="mx-2">|</span>
                <span>Position: {selectedResource.injection_position.replace('_', ' ')}</span>
              </div>
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full h-80 bg-gray-900 text-white font-mono text-sm p-4 rounded border border-gray-700 focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
              />
            </div>
            <div className="p-4 border-t border-gray-700 flex justify-end space-x-2">
              <button
                onClick={() => setSelectedResource(null)}
                className="px-4 py-2 text-sm bg-gray-700 text-white rounded hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdit}
                className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-500"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Dialog */}
      {showCreate && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg w-full max-w-2xl max-h-[90vh] flex flex-col">
            <div className="p-4 border-b border-gray-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Create Resource</h3>
              <button
                onClick={() => setShowCreate(false)}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 p-4 space-y-4 overflow-y-auto">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Name</label>
                <input
                  type="text"
                  value={createForm.name}
                  onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                  placeholder="e.g., main or feature-spec"
                  className="w-full px-3 py-2 bg-gray-900 text-white rounded border border-gray-700 focus:border-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Type</label>
                <select
                  value={createForm.resource_type}
                  onChange={(e) => setCreateForm({ ...createForm, resource_type: e.target.value })}
                  className="w-full px-3 py-2 bg-gray-900 text-white rounded border border-gray-700 focus:border-primary-500"
                >
                  {RESOURCE_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label} - {type.description}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">Content (Markdown)</label>
                <textarea
                  value={createForm.content}
                  onChange={(e) => setCreateForm({ ...createForm, content: e.target.value })}
                  placeholder="# Resource Title&#10;&#10;Content here..."
                  className="w-full h-60 bg-gray-900 text-white font-mono text-sm p-4 rounded border border-gray-700 focus:border-primary-500"
                />
              </div>
            </div>
            <div className="p-4 border-t border-gray-700 flex justify-end space-x-2">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 text-sm bg-gray-700 text-white rounded hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-500"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {/* File Browser Modal */}
      {showFileBrowser && (
        <ProjectFileBrowser
          projectSlug={projectSlug}
          onSelect={handleFileSelect}
          onClose={() => setShowFileBrowser(false)}
        />
      )}
    </div>
  )
}

// Resource Row Component
function ResourceRow({
  resource,
  onSelect,
  onToggleEnabled,
  onToggleInherit,
  onDelete,
}: {
  resource: Resource
  onSelect: () => void
  onToggleEnabled: () => void
  onToggleInherit: () => void
  onDelete: () => void
}) {
  const positionLabel = INJECTION_POSITIONS.find((p) => p.value === resource.injection_position)?.label || resource.injection_position

  return (
    <div className="flex items-center justify-between p-3 bg-gray-700/50 rounded hover:bg-gray-700/70">
      <div className="flex items-center space-x-3">
        <button
          onClick={onToggleEnabled}
          className={`w-4 h-4 rounded border ${
            resource.enabled
              ? 'bg-green-500 border-green-500'
              : 'bg-transparent border-gray-500'
          }`}
          title={resource.enabled ? 'Enabled - click to disable' : 'Disabled - click to enable'}
        />
        <div>
          <button
            onClick={onSelect}
            className="text-white hover:text-primary-400 font-medium"
          >
            {resource.name.split('/').pop()}
          </button>
          <div className="text-xs text-gray-500">
            {resource.file_path} | {positionLabel}
            {resource.inherit_default && (
              <span className="ml-2 text-blue-400">[inherited by default]</span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center space-x-2">
        <button
          onClick={onToggleInherit}
          className={`px-2 py-1 text-xs rounded ${
            resource.inherit_default
              ? 'bg-blue-900/30 text-blue-400'
              : 'bg-gray-600 text-gray-400'
          }`}
          title={resource.inherit_default ? 'Loops inherit by default' : 'Loops do not inherit by default'}
        >
          {resource.inherit_default ? 'Auto' : 'Manual'}
        </button>
        <button
          onClick={onSelect}
          className="px-2 py-1 text-xs bg-gray-600 text-white rounded hover:bg-gray-500"
        >
          Edit
        </button>
        <button
          onClick={onDelete}
          className="px-2 py-1 text-xs bg-red-900/30 text-red-400 rounded hover:bg-red-900/50"
        >
          Delete
        </button>
      </div>
    </div>
  )
}
