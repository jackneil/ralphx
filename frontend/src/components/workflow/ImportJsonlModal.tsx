import { useState, useEffect, useRef } from 'react'
import { listImportFormats, importJsonlToWorkflow, listItems } from '../../api'
import type { ImportFormat, ImportJsonlResponse, WorkflowStep } from '../../api'

interface ImportJsonlModalProps {
  projectSlug: string
  workflowId: string
  steps: WorkflowStep[]
  onClose: () => void
  onImported: (result: ImportJsonlResponse) => void
}

export default function ImportJsonlModal({
  projectSlug,
  workflowId,
  steps,
  onClose,
  onImported,
}: ImportJsonlModalProps) {
  const [formats, setFormats] = useState<ImportFormat[]>([])
  const [selectedFormat, setSelectedFormat] = useState<string>('')
  const [selectedStep, setSelectedStep] = useState<number | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Existing items count for informational purposes
  const [existingItemsCount, setExistingItemsCount] = useState<number>(0)

  // Load import formats and existing items count
  useEffect(() => {
    async function loadFormats() {
      try {
        const data = await listImportFormats(projectSlug)
        setFormats(data)
        // Default to hank_prd if available
        const hankPrd = data.find(f => f.id === 'hank_prd')
        if (hankPrd) {
          setSelectedFormat(hankPrd.id)
        } else if (data.length > 0) {
          setSelectedFormat(data[0].id)
        }
      } catch (err) {
        setError('Failed to load import formats')
      }
    }

    async function loadExistingItems() {
      try {
        // Get total items in the workflow for informational display
        const result = await listItems(projectSlug, {
          workflow_id: workflowId,
          limit: 1, // Just need the total count
        })
        setExistingItemsCount(result.total)
      } catch (err) {
        // Non-critical, continue without count display
        console.warn('Could not load existing items count:', err)
      }
    }

    loadFormats()
    loadExistingItems()
  }, [projectSlug, workflowId])

  // Default to first consumer step
  useEffect(() => {
    const consumerStep = steps.find(s =>
      s.step_type === 'autonomous' &&
      (s.config?.loopType === 'consumer' || !s.config?.loopType)
    )
    if (consumerStep) {
      setSelectedStep(consumerStep.id)
    } else if (steps.length > 0) {
      setSelectedStep(steps[0].id)
    }
  }, [steps])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0]
    if (selectedFile) {
      setFile(selectedFile)
      setError(null)
    }
  }

  const handleImport = async () => {
    if (!file || !selectedFormat || selectedStep === null) {
      setError('Please select a file, format, and target step')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const result = await importJsonlToWorkflow(
        projectSlug,
        workflowId,
        selectedStep,
        selectedFormat,
        file
      )
      onImported(result)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setLoading(false)
    }
  }

  const selectedFormatInfo = formats.find(f => f.id === selectedFormat)

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
      onClick={onClose}
      onKeyDown={(e) => e.key === 'Escape' && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="import-dialog-title"
    >
      <div
        className="card max-w-lg w-full mx-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 id="import-dialog-title" className="text-xl font-semibold text-white mb-4">
          Import Work Items (JSONL)
        </h3>

        {error && (
          <div className="mb-4 p-3 rounded bg-red-900/30 border border-red-800 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Format Selection */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Import Format
          </label>
          <select
            value={selectedFormat}
            onChange={(e) => setSelectedFormat(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
          >
            {formats.map((fmt) => (
              <option key={fmt.id} value={fmt.id}>
                {fmt.label}
              </option>
            ))}
          </select>
          {selectedFormatInfo?.description && (
            <p className="mt-1 text-sm text-gray-500">
              {selectedFormatInfo.description}
            </p>
          )}
        </div>

        {/* Target Step Selection */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Target Step
          </label>
          <select
            value={selectedStep ?? ''}
            onChange={(e) => setSelectedStep(Number(e.target.value))}
            className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-white"
          >
            {steps.map((step) => (
              <option key={step.id} value={step.id}>
                Step {step.step_number}: {step.name}
                {step.step_type === 'autonomous' ? ' (Consumer)' : ''}
              </option>
            ))}
          </select>
          <p className="mt-1 text-sm text-gray-500">
            Items will be available to this step for processing
          </p>
        </div>

        {/* Existing Items Info - Show when there are existing items */}
        {existingItemsCount > 0 && (
          <div className="mb-4 p-4 rounded-lg border bg-gray-800/50 border-gray-700">
            <div className="flex items-start gap-2">
              <svg className="w-5 h-5 text-cyan-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-gray-300">
                  This workflow already has {existingItemsCount} item{existingItemsCount !== 1 ? 's' : ''}.
                </p>
                <p className="text-sm text-gray-500 mt-1">
                  New items will be added alongside existing ones. Items with duplicate IDs will be skipped.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* File Selection */}
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            JSONL File
          </label>
          <div
            className="border-2 border-dashed border-gray-700 rounded-lg p-6 text-center cursor-pointer hover:border-gray-600 transition-colors"
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".jsonl,.json"
              onChange={handleFileChange}
              className="hidden"
            />
            {file ? (
              <div>
                <svg className="w-8 h-8 mx-auto text-green-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <p className="text-white font-medium">{file.name}</p>
                <p className="text-sm text-gray-500">
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
            ) : (
              <div>
                <svg className="w-8 h-8 mx-auto text-gray-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                <p className="text-gray-400">Click to select a JSONL file</p>
                <p className="text-sm text-gray-500 mt-1">or drag and drop</p>
              </div>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end space-x-3">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleImport}
            disabled={loading || !file || !selectedFormat || selectedStep === null}
            className="px-4 py-2 text-white rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed bg-primary-600 hover:bg-primary-500"
          >
            {loading ? 'Importing...' : 'Import Items'}
          </button>
        </div>
      </div>
    </div>
  )
}
