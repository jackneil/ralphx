import { useState, useEffect, useCallback } from 'react'
import {
  listLoopResources,
  createLoopResource,
  updateLoopResource,
  deleteLoopResource,
  browseProjectFiles,
  listLoops,
  type LoopResource,
  type CreateLoopResourceRequest,
} from '../api'

interface LoopResourceManagerProps {
  projectSlug: string
  loopName: string
  loopType: 'planning' | 'implementation' | 'hybrid'
}

// What each resource type does - helpful for users
const RESOURCE_TYPES = [
  {
    value: 'loop_template',
    label: 'Loop Template',
    description: 'The main prompt that drives this loop - tells Claude what to do',
    position: 'template_body',
  },
  {
    value: 'design_doc',
    label: 'Design Doc',
    description: 'Project requirements, specs, or PRD - gives Claude context about what to build',
    position: 'after_design_doc',
  },
  {
    value: 'guardrails',
    label: 'Guardrails',
    description: 'Quality rules and constraints - keeps Claude on track',
    position: 'before_task',
  },
  {
    value: 'custom',
    label: 'Custom Resource',
    description: 'Any other context you want to inject into the prompt',
    position: 'after_task',
  },
]

// Source types with friendly descriptions
const SOURCE_TYPES = [
  {
    value: 'system',
    label: 'Use Default',
    description: 'Use the built-in RalphX template',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    value: 'project_file',
    label: 'From Project',
    description: 'Import from your codebase',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
      </svg>
    ),
  },
  {
    value: 'loop_ref',
    label: 'From Loop',
    description: 'Reference another loop',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
  },
  {
    value: 'inline',
    label: 'Write Custom',
    description: 'Create from scratch',
    icon: (
      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
  },
]

// Icons for resource types
const RESOURCE_ICONS: Record<string, JSX.Element> = {
  loop_template: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
    </svg>
  ),
  design_doc: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  ),
  guardrails: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
    </svg>
  ),
  custom: (
    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
    </svg>
  ),
}

// Redesigned Add Resource Modal
interface AddResourceModalProps {
  addForm: {
    resource_type: string
    name: string
    source_type: string
    source_path: string
    source_loop: string
    source_resource_id: number | null
    inline_content: string
  }
  setAddForm: (form: AddResourceModalProps['addForm']) => void
  onClose: () => void
  onCreate: () => void
  openFileBrowser: () => void
  otherLoops: { name: string; display_name: string }[]
  loopResources: LoopResource[]
}

function AddResourceModal({
  addForm,
  setAddForm,
  onClose,
  onCreate,
  openFileBrowser,
  otherLoops,
  loopResources,
}: AddResourceModalProps) {
  const [step, setStep] = useState<'type' | 'source' | 'config'>('type')

  const selectedType = RESOURCE_TYPES.find(t => t.value === addForm.resource_type)
  const showSystemOption = addForm.resource_type === 'loop_template' || addForm.resource_type === 'guardrails'

  const canProceedToConfig = () => {
    if (addForm.source_type === 'system') return true
    if (addForm.source_type === 'project_file') return !!addForm.source_path
    if (addForm.source_type === 'loop_ref') return !!addForm.source_loop && !!addForm.source_resource_id
    if (addForm.source_type === 'inline') return !!addForm.inline_content
    return false
  }

  const handleBack = () => {
    if (step === 'config') setStep('source')
    else if (step === 'source') setStep('type')
  }

  const handleNext = () => {
    if (step === 'type') setStep('source')
    else if (step === 'source') {
      if (addForm.source_type === 'system') {
        // System defaults don't need config, create directly
        onCreate()
      } else {
        setStep('config')
      }
    }
  }

  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div
        className="bg-[#1a1d23] rounded-xl w-full max-w-2xl shadow-2xl border border-gray-800/50 overflow-hidden"
        style={{
          animation: 'modalSlideIn 0.2s ease-out',
        }}
      >
        <style>{`
          @keyframes modalSlideIn {
            from { opacity: 0; transform: scale(0.95) translateY(10px); }
            to { opacity: 1; transform: scale(1) translateY(0); }
          }
          @keyframes fadeIn {
            from { opacity: 0; transform: translateX(10px); }
            to { opacity: 1; transform: translateX(0); }
          }
          .step-content { animation: fadeIn 0.15s ease-out; }
        `}</style>

        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-800/50 flex items-center justify-between bg-gradient-to-r from-gray-900/50 to-transparent">
          <div className="flex items-center gap-4">
            <h3 className="text-lg font-semibold text-white tracking-tight">Add Resource</h3>
            {/* Step indicator */}
            <div className="flex items-center gap-1.5">
              {['type', 'source', 'config'].map((s, i) => (
                <div
                  key={s}
                  className={`h-1.5 rounded-full transition-all duration-300 ${
                    s === step
                      ? 'w-6 bg-blue-500'
                      : ['type', 'source', 'config'].indexOf(step) > i
                        ? 'w-1.5 bg-blue-500/50'
                        : 'w-1.5 bg-gray-700'
                  }`}
                />
              ))}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-500 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6">
          {/* Step 1: Choose Type */}
          {step === 'type' && (
            <div className="step-content">
              <p className="text-gray-400 text-sm mb-5">What are you adding?</p>
              <div className="grid grid-cols-2 gap-3">
                {RESOURCE_TYPES.map((type) => (
                  <button
                    key={type.value}
                    onClick={() => setAddForm({ ...addForm, resource_type: type.value })}
                    className={`group relative p-4 rounded-lg text-left transition-all duration-150 ${
                      addForm.resource_type === type.value
                        ? 'bg-blue-500/10 border-2 border-blue-500/50 shadow-lg shadow-blue-500/10'
                        : 'bg-gray-800/30 border border-gray-700/50 hover:border-gray-600 hover:bg-gray-800/50'
                    }`}
                  >
                    <div className={`mb-3 p-2 rounded-lg inline-block ${
                      addForm.resource_type === type.value
                        ? 'bg-blue-500/20 text-blue-400'
                        : 'bg-gray-700/50 text-gray-400 group-hover:text-gray-300'
                    }`}>
                      {RESOURCE_ICONS[type.value]}
                    </div>
                    <div className="font-medium text-white mb-1">{type.label}</div>
                    <div className="text-xs text-gray-500 leading-relaxed">{type.description}</div>
                    {addForm.resource_type === type.value && (
                      <div className="absolute top-3 right-3 w-2 h-2 rounded-full bg-blue-500" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Choose Source */}
          {step === 'source' && (
            <div className="step-content">
              <div className="flex items-center gap-2 mb-5">
                <div className={`p-1.5 rounded bg-blue-500/20 text-blue-400`}>
                  {RESOURCE_ICONS[addForm.resource_type]}
                </div>
                <span className="text-sm text-gray-400">
                  {selectedType?.label} <span className="text-gray-600">→</span> Choose source
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {SOURCE_TYPES.filter(t => t.value !== 'system' || showSystemOption).map((source) => (
                  <button
                    key={source.value}
                    onClick={() => setAddForm({ ...addForm, source_type: source.value })}
                    className={`group p-4 rounded-lg text-left transition-all duration-150 ${
                      addForm.source_type === source.value
                        ? 'bg-blue-500/10 border-2 border-blue-500/50'
                        : 'bg-gray-800/30 border border-gray-700/50 hover:border-gray-600 hover:bg-gray-800/50'
                    }`}
                  >
                    <div className={`mb-2 ${
                      addForm.source_type === source.value ? 'text-blue-400' : 'text-gray-500 group-hover:text-gray-400'
                    }`}>
                      {source.icon}
                    </div>
                    <div className="font-medium text-white text-sm">{source.label}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{source.description}</div>
                  </button>
                ))}
              </div>

              {/* Inline config for source */}
              {addForm.source_type === 'project_file' && (
                <div className="mt-4 pt-4 border-t border-gray-800/50">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={addForm.source_path}
                      onChange={(e) => setAddForm({ ...addForm, source_path: e.target.value })}
                      placeholder="path/to/file.md"
                      className="flex-1 px-3 py-2.5 bg-gray-900/50 text-white rounded-lg border border-gray-700/50 focus:border-blue-500/50 focus:outline-none focus:ring-1 focus:ring-blue-500/30 text-sm font-mono placeholder-gray-600"
                    />
                    <button
                      onClick={openFileBrowser}
                      className="px-4 py-2.5 bg-gray-700/50 text-white rounded-lg hover:bg-gray-700 transition-colors text-sm font-medium"
                    >
                      Browse
                    </button>
                  </div>
                </div>
              )}

              {addForm.source_type === 'loop_ref' && (
                <div className="mt-4 pt-4 border-t border-gray-800/50 space-y-3">
                  <select
                    value={addForm.source_loop}
                    onChange={(e) => setAddForm({ ...addForm, source_loop: e.target.value, source_resource_id: null })}
                    className="w-full px-3 py-2.5 bg-gray-900/50 text-white rounded-lg border border-gray-700/50 focus:border-blue-500/50 focus:outline-none text-sm"
                  >
                    <option value="">Select a loop...</option>
                    {otherLoops.map((loop) => (
                      <option key={loop.name} value={loop.name}>
                        {loop.display_name || loop.name}
                      </option>
                    ))}
                  </select>
                  {addForm.source_loop && loopResources.length > 0 && (
                    <select
                      value={addForm.source_resource_id || ''}
                      onChange={(e) => setAddForm({ ...addForm, source_resource_id: e.target.value ? parseInt(e.target.value) : null })}
                      className="w-full px-3 py-2.5 bg-gray-900/50 text-white rounded-lg border border-gray-700/50 focus:border-blue-500/50 focus:outline-none text-sm"
                    >
                      <option value="">Select a resource...</option>
                      {loopResources.map((res) => (
                        <option key={res.id} value={res.id}>
                          {res.name} ({res.resource_type})
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              )}

              {addForm.source_type === 'inline' && (
                <div className="mt-4 pt-4 border-t border-gray-800/50">
                  <textarea
                    value={addForm.inline_content}
                    onChange={(e) => setAddForm({ ...addForm, inline_content: e.target.value })}
                    placeholder="# Your content here..."
                    rows={6}
                    className="w-full px-3 py-2.5 bg-gray-900/50 text-white rounded-lg border border-gray-700/50 focus:border-blue-500/50 focus:outline-none focus:ring-1 focus:ring-blue-500/30 text-sm font-mono placeholder-gray-600 resize-none"
                  />
                </div>
              )}
            </div>
          )}

          {/* Step 3: Config (name) */}
          {step === 'config' && (
            <div className="step-content">
              <div className="flex items-center gap-2 mb-5">
                <div className={`p-1.5 rounded bg-blue-500/20 text-blue-400`}>
                  {RESOURCE_ICONS[addForm.resource_type]}
                </div>
                <span className="text-sm text-gray-400">
                  {selectedType?.label} <span className="text-gray-600">→</span> Final details
                </span>
              </div>

              <div className="bg-gray-800/30 rounded-lg p-4 border border-gray-700/30 mb-4">
                <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Source</div>
                <div className="text-white font-mono text-sm">
                  {addForm.source_type === 'project_file' && addForm.source_path}
                  {addForm.source_type === 'loop_ref' && `${addForm.source_loop} → resource`}
                  {addForm.source_type === 'inline' && `${addForm.inline_content.slice(0, 50)}...`}
                </div>
              </div>

              <div>
                <label className="block text-xs text-gray-500 uppercase tracking-wider mb-2">Name (optional)</label>
                <input
                  type="text"
                  value={addForm.name}
                  onChange={(e) => setAddForm({ ...addForm, name: e.target.value })}
                  placeholder="Auto-generated if empty"
                  className="w-full px-3 py-2.5 bg-gray-900/50 text-white rounded-lg border border-gray-700/50 focus:border-blue-500/50 focus:outline-none focus:ring-1 focus:ring-blue-500/30 text-sm placeholder-gray-600"
                />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-gray-800/50 flex items-center justify-between bg-gray-900/30">
          <button
            onClick={step === 'type' ? onClose : handleBack}
            className="px-4 py-2 text-gray-400 hover:text-white transition-colors text-sm"
          >
            {step === 'type' ? 'Cancel' : '← Back'}
          </button>

          {step === 'config' ? (
            <button
              onClick={onCreate}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors text-sm font-medium"
            >
              Add Resource
            </button>
          ) : (
            <button
              onClick={handleNext}
              disabled={step === 'source' && !canProceedToConfig() && addForm.source_type !== 'system'}
              className="px-5 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-500 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {step === 'source' && addForm.source_type === 'system' ? 'Add Resource' : 'Continue →'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

export default function LoopResourceManager({
  projectSlug,
  loopName,
  loopType,
}: LoopResourceManagerProps) {
  const [resources, setResources] = useState<LoopResource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Add resource dialog
  const [showAdd, setShowAdd] = useState(false)
  const [addForm, setAddForm] = useState<{
    resource_type: string
    name: string
    source_type: string
    source_path: string
    source_loop: string
    source_resource_id: number | null
    inline_content: string
  }>({
    resource_type: 'design_doc',
    name: '',
    source_type: 'project_file',
    source_path: '',
    source_loop: '',
    source_resource_id: null,
    inline_content: '',
  })

  // File browser
  const [showFileBrowser, setShowFileBrowser] = useState(false)
  const [browserPath, setBrowserPath] = useState('')
  const [browserDirs, setBrowserDirs] = useState<string[]>([])
  const [browserFiles, setBrowserFiles] = useState<{ name: string; size: number; extension: string }[]>([])
  const [browserCanGoUp, setBrowserCanGoUp] = useState(false)
  const [browserParent, setBrowserParent] = useState<string | null>(null)

  // Other loops (for loop_ref source)
  const [otherLoops, setOtherLoops] = useState<{ name: string; display_name: string }[]>([])
  const [loopResources, setLoopResources] = useState<LoopResource[]>([])

  // Edit content dialog
  const [editingResource, setEditingResource] = useState<LoopResource | null>(null)
  const [editContent, setEditContent] = useState('')

  // Load resources
  const loadResources = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await listLoopResources(projectSlug, loopName, true)
      setResources(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load resources')
    } finally {
      setLoading(false)
    }
  }, [projectSlug, loopName])

  useEffect(() => {
    loadResources()
  }, [loadResources])

  // Load other loops for loop_ref option
  useEffect(() => {
    async function loadLoops() {
      try {
        const loops = await listLoops(projectSlug)
        setOtherLoops(loops.filter(l => l.name !== loopName))
      } catch {
        // Ignore errors
      }
    }
    loadLoops()
  }, [projectSlug, loopName])

  // When source_loop changes, load that loop's resources
  useEffect(() => {
    async function loadLoopResources() {
      if (addForm.source_loop) {
        try {
          const res = await listLoopResources(projectSlug, addForm.source_loop, false)
          setLoopResources(res)
        } catch {
          setLoopResources([])
        }
      } else {
        setLoopResources([])
      }
    }
    loadLoopResources()
  }, [projectSlug, addForm.source_loop])

  // File browser navigation
  const openFileBrowser = async () => {
    setShowFileBrowser(true)
    try {
      const result = await browseProjectFiles(projectSlug)
      setBrowserPath(result.relative_path || '')
      setBrowserDirs(result.directories)
      setBrowserFiles(result.files)
      setBrowserCanGoUp(result.canGoUp)
      setBrowserParent(result.parent)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to browse files')
    }
  }

  const navigateToDir = async (dir: string) => {
    try {
      const newPath = browserPath ? `${browserPath}/${dir}` : dir
      const result = await browseProjectFiles(projectSlug, newPath)
      setBrowserPath(result.relative_path || newPath)
      setBrowserDirs(result.directories)
      setBrowserFiles(result.files)
      setBrowserCanGoUp(result.canGoUp)
      setBrowserParent(result.parent)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to navigate')
    }
  }

  const navigateUp = async () => {
    if (browserParent !== null) {
      try {
        const result = await browseProjectFiles(projectSlug, browserParent || undefined)
        setBrowserPath(result.relative_path || '')
        setBrowserDirs(result.directories)
        setBrowserFiles(result.files)
        setBrowserCanGoUp(result.canGoUp)
        setBrowserParent(result.parent)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to navigate')
      }
    }
  }

  const selectFile = (filename: string) => {
    const filePath = browserPath ? `${browserPath}/${filename}` : filename
    setAddForm({ ...addForm, source_path: filePath, name: filename.replace(/\.[^/.]+$/, '') })
    setShowFileBrowser(false)
  }

  // Create resource
  const handleCreate = async () => {
    const resourceType = RESOURCE_TYPES.find(t => t.value === addForm.resource_type)
    const request: CreateLoopResourceRequest = {
      resource_type: addForm.resource_type,
      name: addForm.name || addForm.resource_type,
      injection_position: resourceType?.position || 'after_design_doc',
      source_type: addForm.source_type,
    }

    if (addForm.source_type === 'project_file') {
      request.source_path = addForm.source_path
    } else if (addForm.source_type === 'loop_ref') {
      request.source_loop = addForm.source_loop
      request.source_resource_id = addForm.source_resource_id || undefined
    } else if (addForm.source_type === 'inline') {
      request.inline_content = addForm.inline_content
    }

    try {
      await createLoopResource(projectSlug, loopName, request)
      await loadResources()
      setShowAdd(false)
      setAddForm({
        resource_type: 'design_doc',
        name: '',
        source_type: 'project_file',
        source_path: '',
        source_loop: '',
        source_resource_id: null,
        inline_content: '',
      })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create resource')
    }
  }

  // Toggle enabled
  const handleToggle = async (resource: LoopResource) => {
    try {
      await updateLoopResource(projectSlug, loopName, resource.id, {
        enabled: !resource.enabled,
      })
      await loadResources()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to update')
    }
  }

  // Edit inline content
  const handleEditContent = async (resource: LoopResource) => {
    if (resource.source_type === 'inline') {
      setEditingResource(resource)
      setEditContent(resource.content || '')
    }
  }

  const handleSaveContent = async () => {
    if (!editingResource) return
    try {
      await updateLoopResource(projectSlug, loopName, editingResource.id, {
        inline_content: editContent,
      })
      await loadResources()
      setEditingResource(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save')
    }
  }

  // Delete resource
  const handleDelete = async (resource: LoopResource) => {
    if (!window.confirm(`Remove "${resource.name}"? This won't delete any project files.`)) {
      return
    }
    try {
      await deleteLoopResource(projectSlug, loopName, resource.id)
      await loadResources()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete')
    }
  }

  // Get source description for display
  const getSourceDescription = (resource: LoopResource) => {
    switch (resource.source_type) {
      case 'system':
        return 'Using default template'
      case 'project_file':
        return resource.source_path || 'From project file'
      case 'loop_ref':
        return `From loop: ${resource.source_loop}`
      case 'project_resource':
        return 'From project resource'
      case 'inline':
        return 'Custom content'
      default:
        return resource.source_type
    }
  }

  // Determine what resources are recommended for this loop type
  const getRecommendedResources = () => {
    if (loopType === 'planning') {
      return ['loop_template', 'design_doc', 'guardrails']
    } else if (loopType === 'implementation') {
      return ['loop_template', 'design_doc', 'guardrails']
    }
    return ['loop_template']
  }

  const recommendedTypes = getRecommendedResources()
  const hasResource = (type: string) => resources.some(r => r.resource_type === type && r.enabled)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-white">Loop Resources</h3>
          <p className="text-sm text-gray-400">
            Resources are injected into the prompt when this loop runs
          </p>
        </div>
        <button
          onClick={() => setShowAdd(true)}
          className="px-3 py-1.5 text-sm bg-primary-600 text-white rounded hover:bg-primary-500"
        >
          Add Resource
        </button>
      </div>

      {/* Recommendations */}
      <div className="p-4 bg-gray-800/50 rounded-lg border border-gray-700">
        <h4 className="text-sm font-medium text-white mb-3">Quick Setup</h4>
        <div className="flex flex-wrap gap-2">
          {recommendedTypes.map((type) => {
            const typeInfo = RESOURCE_TYPES.find(t => t.value === type)
            const has = hasResource(type)
            return (
              <button
                key={type}
                onClick={() => {
                  if (!has) {
                    // Pre-select this type and open the modal
                    setAddForm({
                      resource_type: type,
                      name: '',
                      source_type: type === 'loop_template' || type === 'guardrails' ? 'system' : 'project_file',
                      source_path: '',
                      source_loop: '',
                      source_resource_id: null,
                      inline_content: '',
                    })
                    setShowAdd(true)
                  }
                }}
                disabled={has}
                className={`flex items-center gap-2 px-3 py-1.5 rounded text-sm transition-all ${
                  has
                    ? 'bg-green-900/30 border border-green-800 text-green-400 cursor-default'
                    : 'bg-gray-700 border border-gray-600 text-gray-400 hover:bg-gray-600 hover:text-gray-300 cursor-pointer'
                }`}
              >
                {has ? (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                )}
                <span>{typeInfo?.label || type}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
          {error}
          <button onClick={() => setError(null)} className="ml-2 underline">
            Dismiss
          </button>
        </div>
      )}

      {/* Resources list */}
      {loading ? (
        <div className="flex items-center justify-center p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500" />
        </div>
      ) : resources.length === 0 ? (
        <div className="text-center py-8 text-gray-400 bg-gray-800/30 rounded-lg border border-dashed border-gray-700">
          <p className="mb-2">No resources configured for this loop yet.</p>
          <p className="text-sm">
            Add a loop template and design doc to get started.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {resources.map((resource) => (
            <div
              key={resource.id}
              className={`p-4 rounded-lg border ${
                resource.enabled
                  ? 'bg-gray-800/50 border-gray-700'
                  : 'bg-gray-800/20 border-gray-800 opacity-60'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start gap-3">
                  <button
                    onClick={() => handleToggle(resource)}
                    className={`mt-1 w-4 h-4 rounded border flex-shrink-0 ${
                      resource.enabled
                        ? 'bg-green-500 border-green-500'
                        : 'bg-transparent border-gray-500'
                    }`}
                    title={resource.enabled ? 'Enabled - click to disable' : 'Disabled - click to enable'}
                  />
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-white font-medium">{resource.name}</span>
                      <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-400">
                        {RESOURCE_TYPES.find(t => t.value === resource.resource_type)?.label ||
                          resource.resource_type}
                      </span>
                    </div>
                    <p className="text-sm text-gray-500 mt-1">{getSourceDescription(resource)}</p>
                    {resource.content && (
                      <p className="text-xs text-gray-600 mt-1 truncate max-w-lg">
                        {resource.content.slice(0, 100)}...
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {resource.source_type === 'inline' && (
                    <button
                      onClick={() => handleEditContent(resource)}
                      className="px-2 py-1 text-xs bg-gray-700 text-white rounded hover:bg-gray-600"
                    >
                      Edit
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(resource)}
                    className="px-2 py-1 text-xs bg-red-900/30 text-red-400 rounded hover:bg-red-900/50"
                  >
                    Remove
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Resource Dialog - Redesigned */}
      {showAdd && (
        <AddResourceModal
          addForm={addForm}
          setAddForm={setAddForm}
          onClose={() => setShowAdd(false)}
          onCreate={handleCreate}
          openFileBrowser={openFileBrowser}
          otherLoops={otherLoops}
          loopResources={loopResources}
        />
      )}

      {/* File Browser Dialog */}
      {showFileBrowser && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]">
          <div className="bg-gray-800 rounded-lg w-full max-w-md mx-4">
            <div className="p-4 border-b border-gray-700 flex justify-between items-center">
              <h4 className="font-medium text-white">Select File</h4>
              <button
                onClick={() => setShowFileBrowser(false)}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-4">
              <div className="text-sm text-gray-400 mb-2">{browserPath || '/ (project root)'}</div>
              <div className="max-h-64 overflow-y-auto space-y-1">
                {browserCanGoUp && (
                  <button
                    onClick={navigateUp}
                    className="w-full text-left px-3 py-2 bg-gray-700 rounded hover:bg-gray-600 text-gray-300"
                  >
                    ..
                  </button>
                )}
                {browserDirs.map((dir) => (
                  <button
                    key={dir}
                    onClick={() => navigateToDir(dir)}
                    className="w-full text-left px-3 py-2 bg-gray-700 rounded hover:bg-gray-600 text-white"
                  >
                    {dir}/
                  </button>
                ))}
                {browserFiles.map((file) => (
                  <button
                    key={file.name}
                    onClick={() => selectFile(file.name)}
                    className="w-full text-left px-3 py-2 bg-gray-700 rounded hover:bg-gray-600 text-white"
                  >
                    {file.name}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Edit Content Dialog */}
      {editingResource && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg w-full max-w-3xl mx-4 max-h-[90vh] flex flex-col">
            <div className="p-4 border-b border-gray-700 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">Edit: {editingResource.name}</h3>
              <button
                onClick={() => setEditingResource(null)}
                className="text-gray-400 hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="flex-1 p-4 overflow-y-auto">
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full h-80 bg-gray-900 text-white font-mono text-sm p-4 rounded border border-gray-700"
              />
            </div>
            <div className="p-4 border-t border-gray-700 flex justify-end gap-2">
              <button
                onClick={() => setEditingResource(null)}
                className="px-4 py-2 text-gray-400 hover:text-white"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveContent}
                className="px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
