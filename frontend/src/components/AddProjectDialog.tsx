import { useState } from 'react'
import { createProject } from '../api'
import DirectoryBrowser from './DirectoryBrowser'

interface AddProjectDialogProps {
  onClose: () => void
  onSuccess: () => void
}

export default function AddProjectDialog({ onClose, onSuccess }: AddProjectDialogProps) {
  const [path, setPath] = useState('')
  const [name, setName] = useState('')
  const [showBrowser, setShowBrowser] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!path.trim()) {
      setError('Path is required')
      return
    }

    setLoading(true)
    setError(null)
    try {
      await createProject({
        path: path.trim(),
        name: name.trim() || undefined,
      })
      onSuccess()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project')
    } finally {
      setLoading(false)
    }
  }

  const handleSelectFromBrowser = (selectedPath: string) => {
    setPath(selectedPath)
    setShowBrowser(false)
    // Auto-generate name from path if not set
    if (!name) {
      const parts = selectedPath.split('/')
      setName(parts[parts.length - 1] || '')
    }
  }

  if (showBrowser) {
    return (
      <DirectoryBrowser
        initialPath={path || undefined}
        onSelect={handleSelectFromBrowser}
        onCancel={() => setShowBrowser(false)}
      />
    )
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg w-full max-w-md">
        {/* Header */}
        <div className="p-4 border-b border-gray-700">
          <h3 className="text-lg font-semibold text-white">Add Project</h3>
          <p className="text-sm text-gray-400 mt-1">
            Add an existing folder as a RalphX project
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Path */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Project Path
            </label>
            <div className="flex space-x-2">
              <input
                type="text"
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/home/user/my-project"
                className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
              />
              <button
                type="button"
                onClick={() => setShowBrowser(true)}
                className="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-gray-300 hover:bg-gray-600"
              >
                Browse
              </button>
            </div>
          </div>

          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Project Name (optional)
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Auto-generated from path"
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
            />
            <p className="text-xs text-gray-500 mt-1">
              Leave empty to use the folder name
            </p>
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end space-x-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !path.trim()}
              className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50"
            >
              {loading ? 'Adding...' : 'Add Project'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
