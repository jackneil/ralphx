import { useState, useEffect } from 'react'
import { getWorkflowExportPreview, exportWorkflow } from '../../api'
import type { ExportPreview, ExportOptions } from '../../api'

interface ExportWorkflowModalProps {
  projectSlug: string
  workflowId: string
  workflowName: string
  onClose: () => void
}

export default function ExportWorkflowModal({
  projectSlug,
  workflowId,
  workflowName,
  onClose,
}: ExportWorkflowModalProps) {
  const [preview, setPreview] = useState<ExportPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Export options
  const [includeRuns, setIncludeRuns] = useState(false)
  const [includePlanning, setIncludePlanning] = useState(true)
  const [stripSecrets, setStripSecrets] = useState(true)

  // Load preview
  useEffect(() => {
    async function loadPreview() {
      try {
        const data = await getWorkflowExportPreview(projectSlug, workflowId)
        setPreview(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load export preview')
      } finally {
        setLoading(false)
      }
    }
    loadPreview()
  }, [projectSlug, workflowId])

  const handleExport = async () => {
    setExporting(true)
    setError(null)

    try {
      const options: ExportOptions = {
        include_runs: includeRuns,
        include_planning: includePlanning,
        strip_secrets: stripSecrets,
      }

      const blob = await exportWorkflow(projectSlug, workflowId, options)

      // Trigger download
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `workflow-${preview?.workflow_id || workflowId}-${new Date().toISOString().slice(0,10)}.ralphx.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="export-dialog-title"
    >
      <div
        className="card max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="export-dialog-title" className="text-xl font-semibold text-white mb-4">
          Export Workflow
        </h3>

        {error && (
          <div className="mb-4 p-3 rounded bg-red-900/30 border border-red-800 text-red-400 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="py-8 text-center text-gray-400">
            Loading export preview...
          </div>
        ) : preview ? (
          <>
            {/* Workflow Info */}
            <div className="mb-6 p-4 rounded-lg bg-gray-800/50 border border-gray-700">
              <h4 className="font-medium text-white mb-2">{workflowName}</h4>
              <div className="grid grid-cols-2 gap-2 text-sm">
                <div className="text-gray-400">Steps:</div>
                <div className="text-white">{preview.steps_count}</div>
                <div className="text-gray-400">Items:</div>
                <div className="text-white">{preview.items_total}</div>
                <div className="text-gray-400">Resources:</div>
                <div className="text-white">{preview.resources_count}</div>
                <div className="text-gray-400">Estimated Size:</div>
                <div className="text-white">{formatSize(preview.estimated_size_bytes)}</div>
              </div>
            </div>

            {/* Secrets Warning */}
            {preview.potential_secrets_detected && (
              <div className="mb-4 p-3 rounded bg-yellow-900/30 border border-yellow-700 text-yellow-400 text-sm">
                <div className="flex items-start space-x-2">
                  <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <div>
                    <strong>Potential secrets detected!</strong>
                    <p className="mt-1 text-yellow-300/80">
                      API keys or credentials may be present in the workflow content.
                      "Strip secrets" is enabled by default.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Export Options */}
            <div className="mb-6 space-y-3">
              <h4 className="text-sm font-medium text-gray-300">Export Options</h4>

              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includePlanning}
                  onChange={(e) => setIncludePlanning(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                />
                <span className="text-gray-300">
                  Include planning session
                  {preview.has_planning_session && (
                    <span className="text-gray-500 ml-1">(available)</span>
                  )}
                </span>
              </label>

              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeRuns}
                  onChange={(e) => setIncludeRuns(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                />
                <span className="text-gray-300">
                  Include execution history
                  {preview.runs_count > 0 && (
                    <span className="text-gray-500 ml-1">({preview.runs_count} runs)</span>
                  )}
                </span>
              </label>

              <label className="flex items-center space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={stripSecrets}
                  onChange={(e) => setStripSecrets(e.target.checked)}
                  className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                />
                <span className="text-gray-300">
                  Strip potential secrets (recommended)
                </span>
              </label>
            </div>

            {/* Warnings */}
            {preview.warnings.length > 0 && (
              <div className="mb-4 p-3 rounded bg-yellow-900/20 border border-yellow-800 text-sm">
                <h5 className="text-yellow-400 font-medium mb-1">Warnings</h5>
                <ul className="list-disc list-inside text-yellow-300/80">
                  {preview.warnings.map((warning, i) => (
                    <li key={i}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}
          </>
        ) : null}

        {/* Actions */}
        <div className="flex justify-end space-x-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleExport}
            disabled={loading || exporting || !preview}
            className="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
          >
            {exporting ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                <span>Exporting...</span>
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                <span>Export</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
