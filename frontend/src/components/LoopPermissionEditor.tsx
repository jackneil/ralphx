import { useState, useEffect, useCallback } from 'react'
import type { LoopPermissions, PermissionTemplateInfo } from '../api'
import {
  getLoopPermissions,
  updateLoopPermissions,
  deleteLoopPermissions,
  listPermissionTemplates,
} from '../api'

interface LoopPermissionEditorProps {
  projectSlug: string
  loopName: string
  onClose: () => void
  onSave?: () => void
}

export default function LoopPermissionEditor({
  projectSlug,
  loopName,
  onClose,
  onSave,
}: LoopPermissionEditorProps) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Current permissions state
  const [permissions, setPermissions] = useState<LoopPermissions | null>(null)
  const [templates, setTemplates] = useState<PermissionTemplateInfo[]>([])

  // Editor state
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')
  const [editMode, setEditMode] = useState<'template' | 'custom'>('template')
  const [jsonContent, setJsonContent] = useState('')
  const [jsonError, setJsonError] = useState<string | null>(null)

  // Load permissions and templates
  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [perms, tmpls] = await Promise.all([
        getLoopPermissions(projectSlug, loopName),
        listPermissionTemplates(),
      ])
      setPermissions(perms)
      setTemplates(tmpls)

      // Set initial editor state based on current permissions
      if (perms.source === 'template' && perms.template_id) {
        setSelectedTemplate(perms.template_id)
        setEditMode('template')
      } else if (perms.source === 'custom') {
        setEditMode('custom')
      } else {
        // Default - use first available template or fallback
        const defaultTemplate = tmpls.length > 0 ? tmpls[0].id : (perms.template_id || '')
        setSelectedTemplate(defaultTemplate)
        setEditMode('template')
      }

      // Initialize JSON content
      setJsonContent(JSON.stringify(perms.permissions, null, 2))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load permissions')
    } finally {
      setLoading(false)
    }
  }, [projectSlug, loopName])

  useEffect(() => {
    loadData()
  }, [loadData])

  // Handle Escape key to close modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !saving) {
        onClose()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose, saving])

  // Validate JSON
  useEffect(() => {
    if (editMode === 'custom') {
      try {
        JSON.parse(jsonContent)
        setJsonError(null)
      } catch {
        setJsonError('Invalid JSON syntax')
      }
    } else {
      setJsonError(null)
    }
  }, [jsonContent, editMode])

  const handleSave = async () => {
    setSaving(true)
    setError(null)

    try {
      if (editMode === 'template') {
        await updateLoopPermissions(projectSlug, loopName, {
          template_id: selectedTemplate,
          permissions: { allow: [] }, // Required but will be overridden by template
        })
      } else {
        // Custom permissions
        const parsed = JSON.parse(jsonContent)
        await updateLoopPermissions(projectSlug, loopName, {
          permissions: parsed,
        })
      }

      onSave?.()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save permissions')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (!confirm('Reset to default permissions? This will remove any custom settings.')) {
      return
    }

    setSaving(true)
    setError(null)

    try {
      await deleteLoopPermissions(projectSlug, loopName)
      await loadData()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to reset permissions')
    } finally {
      setSaving(false)
    }
  }

  const handleTemplateChange = (templateId: string) => {
    setSelectedTemplate(templateId)
    // Don't update jsonContent - it's only used in custom mode
    // The template selection is shown via the dropdown and description
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl border border-gray-700 w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-700">
          <div>
            <h2 className="text-xl font-semibold text-white">Edit Loop Permissions</h2>
            <p className="text-sm text-gray-400 mt-1">
              Configure Claude Code permissions for <span className="text-primary-400">{loopName}</span>
            </p>
          </div>
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
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500"></div>
            </div>
          ) : error ? (
            <div className="p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-400">
              {error}
            </div>
          ) : (
            <>
              {/* Current Status */}
              <div className="p-4 bg-gray-800 rounded-lg">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm text-gray-400">Current Source:</span>
                    <span className={`ml-2 px-2 py-0.5 rounded text-xs font-medium ${
                      permissions?.source === 'custom'
                        ? 'bg-purple-500/20 text-purple-400'
                        : permissions?.source === 'template'
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'bg-gray-700 text-gray-400'
                    }`}>
                      {permissions?.source === 'custom' ? 'Custom' :
                       permissions?.source === 'template' ? `Template: ${permissions?.template_id}` :
                       'Default'}
                    </span>
                  </div>
                  {permissions?.has_custom && (
                    <button
                      onClick={handleReset}
                      disabled={saving}
                      className="text-sm text-gray-400 hover:text-red-400"
                    >
                      Reset to Default
                    </button>
                  )}
                </div>
              </div>

              {/* Edit Mode Toggle */}
              <div className="flex space-x-2">
                <button
                  onClick={() => setEditMode('template')}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                    editMode === 'template'
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-white'
                  }`}
                >
                  Use Template
                </button>
                <button
                  onClick={() => setEditMode('custom')}
                  className={`flex-1 py-2 px-4 rounded-lg text-sm font-medium transition-colors ${
                    editMode === 'custom'
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-white'
                  }`}
                >
                  Custom Permissions
                </button>
              </div>

              {/* Template Selection */}
              {editMode === 'template' && (
                <div className="space-y-4">
                  {templates.length === 0 ? (
                    <div className="p-4 bg-gray-800/50 rounded-lg text-center text-gray-400">
                      <p>No permission templates available.</p>
                      <p className="text-sm mt-1">Switch to Custom mode to define permissions manually.</p>
                    </div>
                  ) : (
                    <>
                      <div>
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          Select Template
                        </label>
                        <select
                          value={selectedTemplate}
                          onChange={(e) => handleTemplateChange(e.target.value)}
                          className="w-full px-4 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
                        >
                          {templates.map((template) => (
                            <option key={template.id} value={template.id}>
                              {template.name}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Template Description */}
                      {templates.find(t => t.id === selectedTemplate) && (
                        <div className="p-4 bg-gray-800/50 rounded-lg">
                          <p className="text-sm text-gray-400">
                            {templates.find(t => t.id === selectedTemplate)?.description}
                          </p>
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {/* Custom JSON Editor */}
              {editMode === 'custom' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-300 mb-2">
                      Permissions JSON
                    </label>
                    <textarea
                      value={jsonContent}
                      onChange={(e) => setJsonContent(e.target.value)}
                      rows={16}
                      className={`w-full px-3 py-2 bg-gray-800 border rounded-lg text-white font-mono text-sm resize-none focus:outline-none ${
                        jsonError
                          ? 'border-red-600 focus:border-red-500'
                          : 'border-gray-600 focus:border-primary-500'
                      }`}
                      placeholder='{"allow": ["Read(**)", "Write(**)", ...], "deny": []}'
                    />
                    {jsonError && (
                      <p className="mt-1 text-sm text-red-400">{jsonError}</p>
                    )}
                  </div>

                  {/* Quick Reference */}
                  <div className="p-4 bg-gray-800/50 rounded-lg">
                    <h4 className="text-sm font-medium text-gray-300 mb-2">Common Patterns</h4>
                    <div className="text-xs text-gray-500 space-y-1 font-mono">
                      <div>Read(**) - Read any file</div>
                      <div>Write(**) - Write any file</div>
                      <div>Edit(**) - Edit any file</div>
                      <div>Bash(*) - Run any bash command</div>
                      <div>Bash(git *) - Run git commands only</div>
                      <div>WebSearch - Enable web search</div>
                    </div>
                  </div>
                </div>
              )}
            </>
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
            disabled={saving || loading || (editMode === 'custom' && !!jsonError) || (editMode === 'template' && templates.length === 0)}
            className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Permissions'}
          </button>
        </div>
      </div>
    </div>
  )
}
