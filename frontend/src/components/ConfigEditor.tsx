import { useEffect, useState } from 'react'
import { getLoopConfig, updateLoopConfig } from '../api'

interface ConfigEditorProps {
  projectSlug: string
  loopName: string
  onClose: () => void
  onSave: () => void
}

export default function ConfigEditor({
  projectSlug,
  loopName,
  onClose,
  onSave,
}: ConfigEditorProps) {
  const [content, setContent] = useState('')
  const [originalContent, setOriginalContent] = useState('')
  const [filePath, setFilePath] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const result = await getLoopConfig(projectSlug, loopName)
        setContent(result.content)
        setOriginalContent(result.content)
        setFilePath(result.path)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load config')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [projectSlug, loopName])

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      await updateLoopConfig(projectSlug, loopName, content)
      setOriginalContent(content)
      onSave()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save config')
    } finally {
      setSaving(false)
    }
  }

  const hasChanges = content !== originalContent

  const handleClose = () => {
    if (hasChanges && !window.confirm('Discard unsaved changes?')) {
      return
    }
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white">Edit Loop Config</h3>
            <p className="text-sm text-gray-400 font-mono truncate">{filePath}</p>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-white"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden p-4">
          {loading ? (
            <div className="h-full flex items-center justify-center text-gray-400">
              Loading config...
            </div>
          ) : (
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className="w-full h-full min-h-[300px] px-4 py-3 bg-gray-900 border border-gray-700 rounded font-mono text-sm text-gray-200 focus:outline-none focus:border-primary-500 resize-none"
              spellCheck={false}
            />
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="px-4 pb-2">
            <div className="p-3 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
              {error}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {hasChanges ? (
              <span className="text-yellow-400">Unsaved changes</span>
            ) : (
              <span>No changes</span>
            )}
          </div>
          <div className="flex space-x-3">
            <button
              onClick={handleClose}
              disabled={saving}
              className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save Config'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
