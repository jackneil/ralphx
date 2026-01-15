import { useEffect, useState, useCallback, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useDashboardStore } from '../stores/dashboard'
import {
  getProject,
  getLoop,
  getLoopStatus,
  getLoopConfig,
  updateLoopConfig,
  listItems,
  listLoops,
  listLoopInputs,
  uploadLoopInput,
  importPasteToLoop,
  deleteLoopInput,
  applyInputTemplate,
  validateLoopInputs,
  type InputFileInfo,
  type ValidationResult,
} from '../api'
import LoopControl from '../components/LoopControl'
import ProgressBar from '../components/ProgressBar'
import SessionTail from '../components/SessionTail'
import { LoopBuilder } from '../components/LoopBuilder'
import { EmptyState, EMPTY_STATE_ICONS } from '../components/Help'
import InputTemplateSelector from '../components/InputTemplateSelector'

const TAG_LABELS: Record<string, string> = {
  master_design: 'Master Design',
  story_instructions: 'Story Instructions',
  stories: 'Stories (JSONL)',
  guardrails: 'Guardrails',
  reference: 'Reference',
}

type TabType = 'overview' | 'items' | 'inputs' | 'runs'

interface LoopDetail {
  name: string
  display_name: string
  type: string
  modes: { name: string; model: string; timeout: number }[]
}

interface LoopStatus {
  is_running: boolean
  run_id?: string
  current_iteration?: number
  current_mode?: string
  status?: string
}

export default function LoopDetail() {
  const { slug, loopName } = useParams<{ slug: string; loopName: string }>()
  const { selectedProject, setSelectedProject, items, itemsTotal, itemsLoading, setItems, setItemsLoading } = useDashboardStore()

  const [loop, setLoop] = useState<LoopDetail | null>(null)
  const [status, setStatus] = useState<LoopStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [showLoopBuilder, setShowLoopBuilder] = useState(false)
  const [initialYaml, setInitialYaml] = useState('')
  const [availableLoops, setAvailableLoops] = useState<string[]>([])
  const [activeTab, setActiveTab] = useState<TabType>('overview')
  const [inputs, setInputs] = useState<InputFileInfo[]>([])
  const [inputsLoading, setInputsLoading] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [pasteContent, setPasteContent] = useState('')
  const [pasteFilename, setPasteFilename] = useState('')
  const [pasteTag, setPasteTag] = useState<string>('')
  const [uploading, setUploading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [showTemplateSelector, setShowTemplateSelector] = useState(false)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const loadStatus = useCallback(async () => {
    if (!slug || !loopName) return
    try {
      const loopStatus = await getLoopStatus(slug, loopName)
      setStatus(loopStatus)
    } catch {
      setStatus({ is_running: false })
    }
  }, [slug, loopName])

  const loadItems = useCallback(async () => {
    if (!slug || !loopName) return
    setItemsLoading(true)
    try {
      // Load items for this specific loop
      const result = await listItems(slug, { source_loop: loopName, limit: 50 })
      setItems(result.items, result.total)
    } catch {
      setItems([], 0)
    } finally {
      setItemsLoading(false)
    }
  }, [slug, loopName, setItems, setItemsLoading])

  const loadInputs = useCallback(async () => {
    if (!slug || !loopName || !loop) return
    setInputsLoading(true)
    try {
      const inputFiles = await listLoopInputs(slug, loopName)
      setInputs(inputFiles)
      // Also load validation
      const loopType = loop.type === 'generator' ? 'planning' : 'implementation'
      const validationResult = await validateLoopInputs(slug, loopName, loopType)
      setValidation(validationResult)
    } catch {
      setInputs([])
      setValidation(null)
    } finally {
      setInputsLoading(false)
    }
  }, [slug, loopName, loop])

  const handleFileUpload = useCallback(async (file: File) => {
    if (!slug || !loopName) return
    setUploading(true)
    setActionError(null)
    try {
      await uploadLoopInput(slug, loopName, file)
      await loadInputs()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }, [slug, loopName, loadInputs])

  const handlePasteImport = useCallback(async () => {
    if (!slug || !loopName || !pasteContent || !pasteFilename) return
    setImporting(true)
    setActionError(null)
    try {
      await importPasteToLoop(slug, loopName, pasteContent, pasteFilename, pasteTag || undefined)
      setPasteContent('')
      setPasteFilename('')
      setPasteTag('')
      setShowImportModal(false)
      await loadInputs()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setImporting(false)
    }
  }, [slug, loopName, pasteContent, pasteFilename, pasteTag, loadInputs])

  const handleApplyTemplate = useCallback(async (templateId: string) => {
    if (!slug || !loopName) return
    setShowTemplateSelector(false)
    setActionError(null)
    try {
      await applyInputTemplate(slug, loopName, templateId)
      await loadInputs()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to apply template')
    }
  }, [slug, loopName, loadInputs])

  const handleDeleteInput = useCallback(async (filename: string) => {
    if (!slug || !loopName) return
    if (!confirm(`Delete ${filename}?`)) return
    setDeleting(filename)
    setActionError(null)
    try {
      await deleteLoopInput(slug, loopName, filename)
      await loadInputs()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeleting(null)
    }
  }, [slug, loopName, loadInputs])

  useEffect(() => {
    if (!slug || !loopName) return

    // Clear stale data immediately when slug/loopName changes
    setLoop(null)
    setStatus(null)
    setItems([], 0)

    async function load() {
      setLoadError(null)
      try {
        const [project, loopDetail] = await Promise.all([
          getProject(slug!),
          getLoop(slug!, loopName!),
        ])
        setSelectedProject(project)
        setLoop(loopDetail)
        await loadStatus()
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : 'Failed to load')
      }
    }

    load()

    // Poll status
    const interval = setInterval(loadStatus, 3000)
    return () => clearInterval(interval)
  }, [slug, loopName, setSelectedProject, loadStatus, setItems])

  // Load tab-specific data when tab changes
  useEffect(() => {
    if (activeTab === 'items') {
      loadItems()
    } else if (activeTab === 'inputs') {
      loadInputs()
    }
  }, [activeTab, loadItems, loadInputs])

  // Handle Escape key for modal
  useEffect(() => {
    if (!showImportModal) return
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !importing) {
        setShowImportModal(false)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [showImportModal, importing])

  if (loadError) {
    return (
      <div className="p-6">
        <div className="card bg-red-900/20 border border-red-800">
          <h2 className="text-lg font-semibold text-red-400 mb-2">Error</h2>
          <p className="text-gray-300 mb-4">{loadError}</p>
          <Link to={slug ? `/projects/${slug}` : '/'} className="btn-secondary inline-block">
            Back to {slug ? 'Project' : 'Dashboard'}
          </Link>
        </div>
      </div>
    )
  }

  if (!loop || !selectedProject) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading...</div>
      </div>
    )
  }

  const isRunning = status?.is_running || false
  const isPaused = status?.status === 'paused'

  const handleEditConfig = useCallback(async () => {
    if (!slug || !loopName) return
    setActionError(null)
    try {
      // Load current config and available loops
      const [config, loops] = await Promise.all([
        getLoopConfig(slug, loopName),
        listLoops(slug),
      ])
      setInitialYaml(config.content)
      setAvailableLoops(loops.map((l) => l.name))
      setShowLoopBuilder(true)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Failed to load config')
    }
  }, [slug, loopName])

  const handleSaveConfig = useCallback(async (yamlContent: string) => {
    if (!slug || !loopName) return
    await updateLoopConfig(slug, loopName, yamlContent)
    // Reload loop config after save
    const loopDetail = await getLoop(slug, loopName)
    setLoop(loopDetail)
    setShowLoopBuilder(false)
  }, [slug, loopName])

  return (
    <div className="p-6">
      {/* Loop Builder Modal */}
      {showLoopBuilder && (
        <LoopBuilder
          projectSlug={slug!}
          loopName={loopName!}
          initialYaml={initialYaml}
          availableLoops={availableLoops}
          onClose={() => setShowLoopBuilder(false)}
          onSave={handleSaveConfig}
        />
      )}

      {/* Breadcrumb */}
      <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
        <Link to="/" className="hover:text-white">Dashboard</Link>
        <span>/</span>
        <Link to={`/projects/${slug}`} className="hover:text-white">
          {selectedProject.name}
        </Link>
        <span>/</span>
        <span className="text-white">{loop.display_name}</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2">{loop.display_name}</h1>
          <p className="text-gray-400">Type: {loop.type}</p>
          <p className="text-gray-500 text-sm font-mono">ID: {loop.name}</p>
        </div>

        <div className="flex items-center space-x-4">
          {/* Edit Config Button */}
          <button
            onClick={handleEditConfig}
            className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <span>Edit Config</span>
          </button>

          {/* Controls */}
          <LoopControl
            projectSlug={slug!}
            loopName={loopName!}
            isRunning={isRunning}
            isPaused={isPaused}
            onStatusChange={loadStatus}
          />
        </div>
      </div>

      {/* Action Error */}
      {actionError && (
        <div className="mb-6 p-3 bg-red-900/30 border border-red-800 rounded flex items-center justify-between">
          <span className="text-sm text-red-400">{actionError}</span>
          <button
            onClick={() => setActionError(null)}
            className="text-red-400 hover:text-red-300"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-700 mb-6">
        <nav className="flex space-x-8">
          {(['overview', 'items', 'inputs', 'runs'] as TabType[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === tab
                  ? 'border-primary-500 text-primary-400'
                  : 'border-transparent text-gray-400 hover:text-gray-300 hover:border-gray-500'
              }`}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'overview' && (
        <>
          {/* Status */}
          <div className="card mb-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-white">Status</h2>
              </div>
              <div className="flex items-center space-x-4">
                <span
                  className={`flex items-center space-x-2 ${
                    isRunning
                      ? isPaused
                        ? 'text-yellow-400'
                        : 'text-green-400'
                      : 'text-gray-400'
                  }`}
                >
                  <span
                    className={`w-3 h-3 rounded-full ${
                      isRunning
                        ? isPaused
                          ? 'bg-yellow-400'
                          : 'bg-green-400 animate-pulse'
                        : 'bg-gray-500'
                    }`}
                  />
                  <span>{isRunning ? (isPaused ? 'Paused' : 'Running') : 'Stopped'}</span>
                </span>
              </div>
            </div>

            {status?.current_iteration && (
              <>
                <div className="mt-4">
                  <ProgressBar
                    value={status.current_iteration}
                    max={100}
                    label={`Progress: Iteration ${status.current_iteration}`}
                    showPercent
                    size="md"
                    color={isRunning ? (isPaused ? 'yellow' : 'green') : 'primary'}
                  />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-sm text-gray-400">Iteration</div>
                    <div className="text-xl font-semibold text-white">
                      {status.current_iteration}
                    </div>
                  </div>
                  <div>
                    <div className="text-sm text-gray-400">Mode</div>
                    <div className="text-xl font-semibold text-white">
                      {status.current_mode || '-'}
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>

          {/* Modes */}
          <div className="card mb-6">
            <h2 className="text-lg font-semibold text-white mb-4">Modes</h2>
            <div className="space-y-2">
              {loop.modes.map((mode) => (
                <div
                  key={mode.name}
                  className={`flex items-center justify-between p-3 rounded-md ${
                    status?.current_mode === mode.name
                      ? 'bg-primary-900/30 border border-primary-600'
                      : 'bg-gray-700'
                  }`}
                >
                  <div>
                    <div className="font-medium text-white">{mode.name}</div>
                    <div className="text-sm text-gray-400">Model: {mode.model}</div>
                  </div>
                  <div className="text-sm text-gray-400">
                    Timeout: {mode.timeout}s
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Live Session Output */}
          {isRunning && (
            <div className="mb-6">
              <SessionTail
                projectSlug={slug!}
                loopName={loopName!}
                enabled={isRunning}
              />
            </div>
          )}
        </>
      )}

      {activeTab === 'items' && (
        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Items</h2>
            <span className="text-sm text-gray-400">{itemsTotal} items</span>
          </div>
          {itemsLoading ? (
            <div className="text-gray-400">Loading items...</div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={EMPTY_STATE_ICONS.inbox}
              title="No items yet"
              description="Items generated by this loop will appear here."
            />
          ) : (
            <div className="space-y-2">
              {items.map((item) => (
                <div key={item.id} className="p-3 bg-gray-700 rounded-md">
                  <div className="flex items-center justify-between mb-1">
                    <span
                      className={`text-xs px-2 py-0.5 rounded ${
                        item.status === 'completed'
                          ? 'bg-green-900 text-green-300'
                          : item.status === 'pending'
                          ? 'bg-yellow-900 text-yellow-300'
                          : 'bg-gray-600 text-gray-300'
                      }`}
                    >
                      {item.status}
                    </span>
                    {item.category && (
                      <span className="text-xs text-gray-400">{item.category}</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-200 line-clamp-2">{item.content}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'inputs' && (
        <div className="space-y-4">
          {/* Validation Banner */}
          {validation && !validation.valid && (
            <div className="p-4 bg-yellow-900/30 border border-yellow-700 rounded-lg">
              <div className="flex items-start space-x-3">
                <svg className="w-5 h-5 text-yellow-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div className="flex-1">
                  <p className="font-medium text-yellow-300">Missing required inputs</p>
                  <div className="mt-2 space-y-2">
                    {validation.missing_tags.map((tag) => (
                      <div key={tag} className="flex items-center justify-between">
                        <span className="text-yellow-400 text-sm">{TAG_LABELS[tag] || tag}</span>
                        <button
                          onClick={() => setShowTemplateSelector(true)}
                          className="text-xs px-2 py-1 bg-yellow-800/50 text-yellow-300 rounded hover:bg-yellow-800"
                        >
                          Add from Templates
                        </button>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-yellow-500 mt-2">
                    Add required inputs or use force start to skip validation.
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="card">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-white">Input Files</h2>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setShowTemplateSelector(true)}
                  className="px-3 py-1.5 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 text-sm"
                >
                  Browse Templates
                </button>
                <button
                  onClick={() => setShowImportModal(true)}
                  className="px-3 py-1.5 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 text-sm"
                >
                  Paste Content
                </button>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="px-3 py-1.5 bg-primary-600 text-white rounded hover:bg-primary-500 text-sm disabled:opacity-50"
                >
                  {uploading ? 'Uploading...' : 'Upload File'}
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="hidden"
                  accept=".md,.txt,.json,.jsonl"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) handleFileUpload(file)
                    e.target.value = ''
                  }}
                />
              </div>
            </div>

            {inputsLoading ? (
              <div className="text-gray-400">Loading...</div>
            ) : inputs.length === 0 ? (
              <EmptyState
                icon={EMPTY_STATE_ICONS.document}
                title="No input files"
                description="Upload design documents, requirements, or other files for this loop to process."
                action={{
                  label: 'Browse Templates',
                  onClick: () => setShowTemplateSelector(true),
                }}
              />
            ) : (
              <div className="space-y-2">
                {inputs.map((input) => (
                  <div
                    key={input.name}
                    className="flex items-center justify-between p-3 bg-gray-700 rounded-md"
                  >
                    <div className="flex items-center space-x-3">
                      <div>
                        <div className="font-medium text-white">{input.name}</div>
                        <div className="text-xs text-gray-400">
                          {(input.size / 1024).toFixed(1)} KB
                        </div>
                      </div>
                      {input.tag && (
                        <span className="px-2 py-0.5 text-xs bg-gray-600 text-gray-300 rounded">
                          {TAG_LABELS[input.tag] || input.tag}
                        </span>
                      )}
                    </div>
                    <button
                      onClick={() => handleDeleteInput(input.name)}
                      disabled={deleting === input.name}
                      className="p-1 text-gray-400 hover:text-red-400 disabled:opacity-50"
                      title="Delete"
                    >
                      {deleting === input.name ? (
                        <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'runs' && (
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-4">Run History</h2>
          <Link
            to={`/projects/${slug}/runs?loop=${loopName}`}
            className="text-primary-400 hover:text-primary-300"
          >
            View all runs for this loop
          </Link>
        </div>
      )}

      {/* Import Modal */}
      {showImportModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget && !importing) {
              setShowImportModal(false)
            }
          }}
        >
          <div className="bg-gray-800 rounded-lg p-6 w-full max-w-lg mx-4">
            <h3 className="text-lg font-semibold text-white mb-4">Paste Content</h3>
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-gray-400 mb-1">Filename</label>
                <input
                  type="text"
                  value={pasteFilename}
                  onChange={(e) => setPasteFilename(e.target.value)}
                  placeholder="design-doc.md"
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                  disabled={importing}
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Tag (optional)</label>
                <select
                  value={pasteTag}
                  onChange={(e) => setPasteTag(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white"
                  disabled={importing}
                >
                  <option value="">No tag</option>
                  <option value="master_design">Master Design</option>
                  <option value="story_instructions">Story Instructions</option>
                  <option value="stories">Stories (JSONL)</option>
                  <option value="guardrails">Guardrails</option>
                  <option value="reference">Reference</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1">Content</label>
                <textarea
                  value={pasteContent}
                  onChange={(e) => setPasteContent(e.target.value)}
                  placeholder="Paste your content here..."
                  rows={10}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white font-mono text-sm"
                  disabled={importing}
                />
              </div>
            </div>
            <div className="flex justify-end space-x-3 mt-6">
              <button
                onClick={() => setShowImportModal(false)}
                disabled={importing}
                className="px-4 py-2 text-gray-400 hover:text-white disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handlePasteImport}
                disabled={!pasteContent || !pasteFilename || importing}
                className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {importing ? 'Importing...' : 'Import'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Template Selector Modal */}
      {showTemplateSelector && loop && (
        <InputTemplateSelector
          loopType={loop.type === 'generator' ? 'planning' : 'implementation'}
          onSelect={handleApplyTemplate}
          onCancel={() => setShowTemplateSelector(false)}
        />
      )}
    </div>
  )
}
