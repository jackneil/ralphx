import { useState, useRef, useEffect } from 'react'
import { getWorkflowImportPreview, importWorkflow } from '../../api'
import type { ImportPreview, ImportResult, ImportOptions } from '../../api'

interface ImportWorkflowModalProps {
  projectSlug: string
  onClose: () => void
  onImported: (result: ImportResult) => void
}

export default function ImportWorkflowModal({
  projectSlug,
  onClose,
  onImported,
}: ImportWorkflowModalProps) {
  const [step, setStep] = useState<'upload' | 'preview' | 'importing'>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Selected steps (by step_number) and resources (by id)
  const [selectedSteps, setSelectedSteps] = useState<Set<number>>(new Set())
  const [selectedResourceIds, setSelectedResourceIds] = useState<Set<number>>(new Set())
  const [importPlanning, setImportPlanning] = useState(true)
  const [importRuns, setImportRuns] = useState(false)
  const [conflictResolution, setConflictResolution] = useState<'skip' | 'rename' | 'overwrite'>('rename')

  // Initialize selections when preview is loaded
  useEffect(() => {
    if (preview) {
      // Select all steps by default
      setSelectedSteps(new Set(preview.steps.map(s => s.step_number)))
      // Select all resources by default
      setSelectedResourceIds(new Set(preview.resources.map(r => r.id)))
    }
  }, [preview])

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (!selectedFile) return

    setFile(selectedFile)
    setError(null)
    setLoading(true)

    try {
      const previewData = await getWorkflowImportPreview(projectSlug, selectedFile)
      setPreview(previewData)
      setStep('preview')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read file')
    } finally {
      setLoading(false)
    }
  }

  const handleImport = async () => {
    if (!file) return

    setStep('importing')
    setError(null)

    try {
      const options: ImportOptions = {
        conflict_resolution: conflictResolution,
        import_items: selectedSteps.size > 0,
        import_resources: selectedResourceIds.size > 0,
        import_planning: importPlanning,
        import_runs: importRuns,
        selected_steps: Array.from(selectedSteps),
        selected_resource_ids: Array.from(selectedResourceIds),
      }

      const result = await importWorkflow(projectSlug, file, options)
      onImported(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
      setStep('preview')
    }
  }

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault()
    const droppedFile = e.dataTransfer.files[0]
    if (droppedFile?.name.endsWith('.zip')) {
      setFile(droppedFile)
      setError(null)
      setLoading(true)

      try {
        const previewData = await getWorkflowImportPreview(projectSlug, droppedFile)
        setPreview(previewData)
        setStep('preview')
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to read file')
      } finally {
        setLoading(false)
      }
    } else {
      setError('Please drop a .ralphx.zip file')
    }
  }

  // Toggle step selection
  const toggleStep = (stepNumber: number) => {
    setSelectedSteps(prev => {
      const newSet = new Set(prev)
      if (newSet.has(stepNumber)) {
        newSet.delete(stepNumber)
      } else {
        newSet.add(stepNumber)
      }
      return newSet
    })
  }

  // Toggle resource selection
  const toggleResource = (resourceId: number) => {
    setSelectedResourceIds(prev => {
      const newSet = new Set(prev)
      if (newSet.has(resourceId)) {
        newSet.delete(resourceId)
      } else {
        newSet.add(resourceId)
      }
      return newSet
    })
  }

  // Toggle all steps
  const toggleAllSteps = () => {
    if (preview) {
      if (selectedSteps.size === preview.steps.length) {
        setSelectedSteps(new Set())
      } else {
        setSelectedSteps(new Set(preview.steps.map(s => s.step_number)))
      }
    }
  }

  // Toggle all resources
  const toggleAllResources = () => {
    if (preview) {
      if (selectedResourceIds.size === preview.resources.length) {
        setSelectedResourceIds(new Set())
      } else {
        setSelectedResourceIds(new Set(preview.resources.map(r => r.id)))
      }
    }
  }

  // Calculate total items from selected steps
  const selectedItemsCount = preview
    ? preview.steps
        .filter(s => selectedSteps.has(s.step_number))
        .reduce((sum, s) => sum + s.items_count, 0)
    : 0

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-workflow-dialog-title"
    >
      <div
        className="card max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="import-workflow-dialog-title" className="text-xl font-semibold text-white mb-4">
          Import Workflow
        </h3>

        {/* Progress Indicator */}
        <div className="flex items-center justify-center mb-6 text-sm">
          <span className={`${step === 'upload' ? 'text-cyan-400 font-medium' : 'text-gray-500'}`}>
            1. Upload
          </span>
          <span className="mx-2 text-gray-600">→</span>
          <span className={`${step === 'preview' ? 'text-cyan-400 font-medium' : 'text-gray-500'}`}>
            2. Preview
          </span>
          <span className="mx-2 text-gray-600">→</span>
          <span className={`${step === 'importing' ? 'text-cyan-400 font-medium' : 'text-gray-500'}`}>
            3. Import
          </span>
        </div>

        {error && (
          <div className="mb-4 p-3 rounded bg-red-900/30 border border-red-800 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Upload Step */}
        {step === 'upload' && (
          <>
            <div
              className="border-2 border-dashed border-gray-700 rounded-lg p-8 text-center cursor-pointer hover:border-gray-600 transition-colors"
              onClick={() => fileInputRef.current?.click()}
              onDrop={handleDrop}
              onDragOver={(e) => e.preventDefault()}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip"
                onChange={handleFileChange}
                className="hidden"
              />
              {loading ? (
                <div>
                  <svg className="w-10 h-10 mx-auto text-cyan-400 mb-3 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <p className="text-gray-400">Reading file...</p>
                </div>
              ) : (
                <div>
                  <svg className="w-10 h-10 mx-auto text-gray-500 mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  <p className="text-white font-medium">Drop a workflow export here</p>
                  <p className="text-sm text-gray-500 mt-1">or click to browse</p>
                  <p className="text-xs text-gray-600 mt-2">Accepts .ralphx.zip files</p>
                </div>
              )}
            </div>

            <div className="flex justify-end mt-6">
              <button
                onClick={onClose}
                className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
              >
                Cancel
              </button>
            </div>
          </>
        )}

        {/* Preview Step */}
        {step === 'preview' && preview && (
          <>
            {/* Workflow Info */}
            <div className="mb-6 p-4 rounded-lg bg-gray-800/50 border border-gray-700">
              <h4 className="font-medium text-white mb-2">{preview.workflow_name}</h4>
              <div className="text-sm text-gray-400">
                <span>Exported: {new Date(preview.exported_at).toLocaleDateString()}</span>
                <span className="mx-2">•</span>
                <span>RalphX {preview.ralphx_version}</span>
              </div>
            </div>

            {/* Compatibility */}
            {!preview.is_compatible && (
              <div className="mb-4 p-3 rounded bg-red-900/30 border border-red-800 text-red-400 text-sm">
                <strong>Compatibility Issues</strong>
                <ul className="list-disc list-inside mt-1">
                  {preview.compatibility_notes.map((note, i) => (
                    <li key={i}>{note}</li>
                  ))}
                </ul>
              </div>
            )}

            {preview.is_compatible && preview.compatibility_notes.length > 0 && (
              <div className="mb-4 p-3 rounded bg-yellow-900/20 border border-yellow-800 text-yellow-400 text-sm">
                <strong>Notes</strong>
                <ul className="list-disc list-inside mt-1">
                  {preview.compatibility_notes.map((note, i) => (
                    <li key={i}>{note}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Secrets Warning */}
            {preview.potential_secrets_detected && (
              <div className="mb-4 p-3 rounded bg-yellow-900/30 border border-yellow-700 text-yellow-400 text-sm">
                <div className="flex items-start space-x-2">
                  <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <span>This export may contain secrets or credentials.</span>
                </div>
              </div>
            )}

            {/* Select What to Import - Tree Style */}
            <div className="mb-6 space-y-2">
              <h4 className="text-sm font-medium text-gray-300 mb-3">Select what to import:</h4>

              {/* Steps Section */}
              {preview.steps.length > 0 && (
                <div className="space-y-1">
                  {/* Steps parent checkbox */}
                  <label className="flex items-center space-x-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedSteps.size === preview.steps.length && preview.steps.length > 0}
                      ref={(el) => {
                        if (el) {
                          el.indeterminate = selectedSteps.size > 0 && selectedSteps.size < preview.steps.length
                        }
                      }}
                      onChange={toggleAllSteps}
                      className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                    />
                    <span className="text-gray-300">
                      Steps ({preview.steps.length})
                    </span>
                  </label>

                  {/* Individual steps */}
                  <div className="ml-7 space-y-1">
                    {preview.steps.map((s) => (
                      <label key={s.step_number} className="flex items-center space-x-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedSteps.has(s.step_number)}
                          onChange={() => toggleStep(s.step_number)}
                          className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                        />
                        <span className="text-gray-400">
                          {s.name} - <span className="text-gray-500">{s.items_count} items</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Resources Section */}
              {preview.resources.length > 0 && (
                <div className="space-y-1 mt-3">
                  {/* Resources parent checkbox */}
                  <label className="flex items-center space-x-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedResourceIds.size === preview.resources.length && preview.resources.length > 0}
                      ref={(el) => {
                        if (el) {
                          el.indeterminate = selectedResourceIds.size > 0 && selectedResourceIds.size < preview.resources.length
                        }
                      }}
                      onChange={toggleAllResources}
                      className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                    />
                    <span className="text-gray-300">
                      Resources ({preview.resources.length})
                    </span>
                  </label>

                  {/* Individual resources */}
                  <div className="ml-7 space-y-1">
                    {preview.resources.map((r) => (
                      <label key={r.id} className="flex items-center space-x-3 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedResourceIds.has(r.id)}
                          onChange={() => toggleResource(r.id)}
                          className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                        />
                        <span className="text-gray-400">
                          {r.name}
                          <span className="text-gray-600 text-xs ml-2">({r.resource_type})</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              )}

              {/* Planning Session */}
              {preview.has_planning_session && (
                <label className="flex items-center space-x-3 cursor-pointer mt-3">
                  <input
                    type="checkbox"
                    checked={importPlanning}
                    onChange={(e) => setImportPlanning(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                  />
                  <span className="text-gray-300">
                    Planning Session
                  </span>
                </label>
              )}

              {/* Execution History */}
              {preview.has_runs && (
                <label className="flex items-center space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={importRuns}
                    onChange={(e) => setImportRuns(e.target.checked)}
                    className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-cyan-500 focus:ring-cyan-500"
                  />
                  <span className="text-gray-300">
                    Execution History
                  </span>
                </label>
              )}
            </div>

            {/* Selection Summary */}
            <div className="mb-4 text-sm text-gray-500">
              Will import: {selectedSteps.size} step{selectedSteps.size !== 1 ? 's' : ''} ({selectedItemsCount} items), {selectedResourceIds.size} resource{selectedResourceIds.size !== 1 ? 's' : ''}
              {importPlanning && preview.has_planning_session ? ', planning session' : ''}
              {importRuns && preview.has_runs ? ', execution history' : ''}
            </div>

            {/* Conflict Resolution */}
            <div className="mb-6">
              <h4 className="text-sm font-medium text-gray-300 mb-2">If conflicts occur</h4>
              <select
                value={conflictResolution}
                onChange={(e) => setConflictResolution(e.target.value as 'skip' | 'rename' | 'overwrite')}
                className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
              >
                <option value="rename">Rename (add suffix)</option>
                <option value="skip">Skip conflicting items</option>
                <option value="overwrite">Overwrite existing</option>
              </select>
            </div>

            {/* Actions */}
            <div className="flex justify-between">
              <button
                onClick={() => {
                  setStep('upload')
                  setFile(null)
                  setPreview(null)
                }}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              >
                Choose different file
              </button>
              <div className="flex space-x-3">
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleImport}
                  disabled={!preview.is_compatible || (selectedSteps.size === 0 && selectedResourceIds.size === 0)}
                  className="px-4 py-2 bg-cyan-600 text-white rounded hover:bg-cyan-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                  </svg>
                  <span>Import as New Workflow</span>
                </button>
              </div>
            </div>
          </>
        )}

        {/* Importing Step */}
        {step === 'importing' && (
          <div className="py-8 text-center">
            <svg className="w-12 h-12 mx-auto text-cyan-400 mb-4 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <p className="text-white font-medium">Importing workflow...</p>
            <p className="text-sm text-gray-500 mt-1">This may take a moment</p>
          </div>
        )}
      </div>
    </div>
  )
}
