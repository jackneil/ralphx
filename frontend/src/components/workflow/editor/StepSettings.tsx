import { useState, useEffect, useCallback } from 'react'
import type { WorkflowStep, TemplateVariableInfo, DesignDocFile } from '../../../api'
import { getDefaultStepPrompt, listDesignDocFiles, createDesignDocFile } from '../../../api'
import { validatePrompt, isPromptModified } from '../../../utils/promptValidation'

// Processing type definitions with their associated settings
type ProcessingType = 'design_doc' | 'extractgen_requirements' | 'webgen_requirements' | 'implementation'

interface ExecutionDefaults {
  model: 'sonnet' | 'opus' | 'haiku' | 'sonnet-1m'
  timeout: number
  max_iterations?: number
  cooldown_between_iterations?: number
  max_consecutive_errors?: number
}

interface ProcessingTypeConfig {
  label: string
  description: string
  icon: 'chat' | 'list' | 'code' | 'search'
  step_type: 'interactive' | 'autonomous'
  loopType: string
  template?: string  // Optional template name for workflow_executor
  defaultTools: string[]
  defaults: ExecutionDefaults
}

const PROCESSING_TYPES: Record<ProcessingType, ProcessingTypeConfig> = {
  design_doc: {
    label: 'Build Design Doc',
    description: 'Interactive chat with web research to create a comprehensive design document',
    icon: 'chat',
    step_type: 'interactive',
    loopType: 'design_doc',
    defaultTools: ['WebSearch', 'WebFetch', 'Bash', 'Read', 'Glob', 'Grep', 'Edit', 'Write'],  // Web research + codebase exploration + file editing
    defaults: {
      model: 'opus',
      timeout: 300,  // Per-response timeout (interactive)
    },
  },
  extractgen_requirements: {
    label: 'Generate Stories (Extract)',
    description: 'Extract user stories from design documents',
    icon: 'list',
    step_type: 'autonomous',
    loopType: 'generator',
    template: 'extractgen_requirements',
    defaultTools: ['WebSearch', 'WebFetch'],
    defaults: {
      model: 'opus',
      timeout: 600,
      max_iterations: 100,
      cooldown_between_iterations: 5,
      max_consecutive_errors: 5,
    },
  },
  webgen_requirements: {
    label: 'Generate Stories (WebSearch)',
    description: 'Discover missing requirements via web research',
    icon: 'search',
    step_type: 'autonomous',
    loopType: 'generator',
    template: 'webgen_requirements',
    defaultTools: ['WebSearch', 'WebFetch'],
    defaults: {
      model: 'opus',
      timeout: 900,  // Higher for web research
      max_iterations: 15,  // Lower - web research is expensive
      cooldown_between_iterations: 15,  // Rate limit protection
      max_consecutive_errors: 3,
    },
  },
  implementation: {
    label: 'Implementation',
    description: 'Consumes stories and commits code to git',
    icon: 'code',
    step_type: 'autonomous',
    loopType: 'consumer',
    template: 'implementation',
    defaultTools: ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep'],
    defaults: {
      model: 'opus',
      timeout: 1800,  // Implementation takes longer
      max_iterations: 50,
      cooldown_between_iterations: 5,
      max_consecutive_errors: 3,
    },
  },
}

// All available tools for checkbox list
const ALL_TOOLS = [
  { id: 'WebSearch', label: 'WebSearch', description: 'Web search for research' },
  { id: 'WebFetch', label: 'WebFetch', description: 'Fetch web page content' },
  { id: 'Read', label: 'Read', description: 'Read files from the codebase' },
  { id: 'Write', label: 'Write', description: 'Write new files' },
  { id: 'Edit', label: 'Edit', description: 'Edit existing files' },
  { id: 'Bash', label: 'Bash', description: 'Run shell commands' },
  { id: 'Glob', label: 'Glob', description: 'File pattern matching' },
  { id: 'Grep', label: 'Grep', description: 'Search file contents' },
  { id: 'NotebookEdit', label: 'NotebookEdit', description: 'Edit Jupyter notebooks' },
]

// Default values for run limits
const DEFAULTS = {
  max_iterations: 100,
  cooldown_between_iterations: 5,
  max_consecutive_errors: 5,
}

function getProcessingType(step: WorkflowStep): ProcessingType {
  const loopType = step.config?.loopType
  const template = step.config?.template
  if (loopType === 'design_doc' || step.step_type === 'interactive') return 'design_doc'
  if (template === 'webgen_requirements') return 'webgen_requirements'
  // Handle both new name and legacy "research" template from old database records
  if (template === 'extractgen_requirements' || template === 'research' || loopType === 'generator' || loopType === 'planning') return 'extractgen_requirements'
  return 'implementation' // implementation, consumer, or default
}

// Detect which fields have been modified from the current type's defaults
function getModifiedFields(step: WorkflowStep, currentType: ProcessingType): string[] {
  const typeConfig = PROCESSING_TYPES[currentType]
  const defaults = typeConfig.defaults
  const config = step.config || {}
  const modified: string[] = []

  // Check execution settings
  if (config.model && config.model !== defaults.model) {
    modified.push(`AI Model (${config.model})`)
  }
  if (config.timeout && config.timeout !== defaults.timeout) {
    modified.push(`Timeout (${config.timeout}s)`)
  }
  if (config.max_iterations !== undefined && config.max_iterations !== defaults.max_iterations) {
    modified.push(`Max Iterations (${config.max_iterations})`)
  }
  if (config.cooldown_between_iterations !== undefined &&
      config.cooldown_between_iterations !== defaults.cooldown_between_iterations) {
    modified.push(`Cooldown (${config.cooldown_between_iterations}s)`)
  }
  if (config.max_consecutive_errors !== undefined &&
      config.max_consecutive_errors !== defaults.max_consecutive_errors) {
    modified.push(`Max Errors (${config.max_consecutive_errors})`)
  }

  // Check custom prompt
  if (config.customPrompt) {
    modified.push('Custom AI Instructions')
  }

  // Check context_from_steps
  if (config.context_from_steps && config.context_from_steps.length > 0) {
    modified.push(`Context from Steps (${config.context_from_steps.length} selected)`)
  }

  // Check tools - compare sorted arrays
  // Only consider tools modified if allowedTools was explicitly set (not undefined)
  // An undefined allowedTools means "use defaults" and shouldn't trigger modification warning
  if (config.allowedTools !== undefined) {
    const defaultTools = [...typeConfig.defaultTools].sort()
    const currentTools = [...config.allowedTools].sort()
    if (JSON.stringify(currentTools) !== JSON.stringify(defaultTools)) {
      modified.push('Tool Selection')
    }
  }

  return modified
}

interface StepSettingsProps {
  step: WorkflowStep
  projectSlug: string
  allSteps: WorkflowStep[]
  onChange: (step: WorkflowStep) => void
}

export default function StepSettings({ step, projectSlug, allSteps, onChange }: StepSettingsProps) {
  const currentProcessingType = getProcessingType(step)
  const currentTypeConfig = PROCESSING_TYPES[currentProcessingType]

  // Lock processing type if any iterations have been run
  const hasIterations = (step.iterations_completed || 0) > 0 || (step.items_generated || 0) > 0
  const isProcessingTypeLocked = hasIterations

  // Design doc file state (for design_doc processing type)
  const [designDocFiles, setDesignDocFiles] = useState<DesignDocFile[]>([])
  const [loadingDesignDocFiles, setLoadingDesignDocFiles] = useState(false)
  const [showCreateFileModal, setShowCreateFileModal] = useState(false)
  const [newFileName, setNewFileName] = useState('')
  const [creatingFile, setCreatingFile] = useState(false)

  // AI Instructions (Advanced) state
  const [promptExpanded, setPromptExpanded] = useState(false)
  const [defaultPrompt, setDefaultPrompt] = useState('')
  const [promptVariables, setPromptVariables] = useState<TemplateVariableInfo[]>([])
  const [loadingPrompt, setLoadingPrompt] = useState(false)
  const [promptError, setPromptError] = useState<string | null>(null)
  const [showVariables, setShowVariables] = useState(false)
  const [showResetConfirm, setShowResetConfirm] = useState(false)

  // Type change confirmation dialog state
  const [showTypeChangeConfirm, setShowTypeChangeConfirm] = useState(false)
  const [pendingTypeChange, setPendingTypeChange] = useState<ProcessingType | null>(null)
  const [modifiedFieldsList, setModifiedFieldsList] = useState<string[]>([])

  // Derived prompt state
  const isUsingCustomPrompt = !!step.config?.customPrompt
  const displayedPrompt = step.config?.customPrompt || defaultPrompt
  const loopType = step.config?.loopType || 'consumer'

  // Validation state
  const validation = isUsingCustomPrompt
    ? validatePrompt(step.config?.customPrompt || '', loopType, promptVariables)
    : { isValid: true, missingRequired: [], missingOptional: [], warnings: [] }

  // Can edit prompt only if step is not running
  const isStepRunning = step.status === 'active' && step.has_active_run
  const canEditPrompt = !isStepRunning

  // Fetch default prompt when loop type changes
  const fetchDefaultPrompt = useCallback(async () => {
    if (step.step_type !== 'autonomous') return
    if (currentProcessingType === 'design_doc') return

    setLoadingPrompt(true)
    setPromptError(null)

    try {
      const data = await getDefaultStepPrompt(loopType)
      setDefaultPrompt(data.prompt)
      setPromptVariables(data.variables)
    } catch (err) {
      setPromptError('Failed to load default prompt')
      console.error('Error fetching default prompt:', err)
    } finally {
      setLoadingPrompt(false)
    }
  }, [step.step_type, currentProcessingType, loopType])

  useEffect(() => {
    fetchDefaultPrompt()
  }, [fetchDefaultPrompt])

  // Load design doc files when processing type is design_doc
  const loadDesignDocFiles = useCallback(async () => {
    if (currentProcessingType !== 'design_doc') return
    setLoadingDesignDocFiles(true)
    try {
      const files = await listDesignDocFiles(projectSlug)
      setDesignDocFiles(files)
    } catch (err) {
      console.error('Failed to load design doc files:', err)
    } finally {
      setLoadingDesignDocFiles(false)
    }
  }, [projectSlug, currentProcessingType])

  useEffect(() => {
    loadDesignDocFiles()
  }, [loadDesignDocFiles])

  const handleCreateFile = async () => {
    if (!newFileName.trim() || creatingFile) return
    setCreatingFile(true)
    try {
      const file = await createDesignDocFile(projectSlug, newFileName.trim())
      // Select the newly created file
      updateConfig({ design_doc_path: file.name })
      setShowCreateFileModal(false)
      setNewFileName('')
      // Refresh file list
      await loadDesignDocFiles()
    } catch (err) {
      console.error('Failed to create file:', err)
    } finally {
      setCreatingFile(false)
    }
  }

  const updateConfig = useCallback((updates: Partial<NonNullable<WorkflowStep['config']>>) => {
    onChange({
      ...step,
      config: {
        ...step.config,
        ...updates,
      },
    })
  }, [onChange, step])

  // Clear custom prompt when switching to interactive (design_doc) processing type
  useEffect(() => {
    if (step.config?.customPrompt && currentProcessingType === 'design_doc') {
      updateConfig({ customPrompt: undefined })
    }
  }, [currentProcessingType, step.config?.customPrompt, updateConfig])

  const handleProcessingTypeChange = (type: ProcessingType) => {
    const typeConfig = PROCESSING_TYPES[type]
    // Preserve context_from_steps when switching between generator types that both support it
    const isGeneratorType = (t: ProcessingType) => t === 'extractgen_requirements' || t === 'webgen_requirements'
    const preserveContext = isGeneratorType(currentProcessingType) && isGeneratorType(type)
    onChange({
      ...step,
      step_type: typeConfig.step_type,
      config: {
        // Only preserve non-execution settings
        description: step.config?.description,
        skippable: step.config?.skippable,
        // Reset to new type's defaults
        loopType: typeConfig.loopType,
        template: typeConfig.template,
        allowedTools: typeConfig.defaultTools,
        model: typeConfig.defaults.model,
        timeout: typeConfig.defaults.timeout,
        max_iterations: typeConfig.defaults.max_iterations,
        cooldown_between_iterations: typeConfig.defaults.cooldown_between_iterations,
        max_consecutive_errors: typeConfig.defaults.max_consecutive_errors,
        customPrompt: undefined,  // Always clear custom prompt on type change
        // Preserve context_from_steps when switching between generator types
        context_from_steps: preserveContext ? step.config?.context_from_steps : undefined,
      },
    })
  }

  // Handle click on processing type button - check for modifications first
  const handleProcessingTypeClick = (type: ProcessingType) => {
    if (isProcessingTypeLocked) return
    if (type === currentProcessingType) return

    const modified = getModifiedFields(step, currentProcessingType)
    if (modified.length > 0) {
      // Show confirmation dialog
      setModifiedFieldsList(modified)
      setPendingTypeChange(type)
      setShowTypeChangeConfirm(true)
    } else {
      // No modifications, change directly
      handleProcessingTypeChange(type)
    }
  }

  // Confirm type change (from dialog)
  const confirmTypeChange = () => {
    if (pendingTypeChange) {
      handleProcessingTypeChange(pendingTypeChange)
    }
    setShowTypeChangeConfirm(false)
    setPendingTypeChange(null)
    setModifiedFieldsList([])
  }

  // Cancel type change (from dialog)
  const cancelTypeChange = () => {
    setShowTypeChangeConfirm(false)
    setPendingTypeChange(null)
    setModifiedFieldsList([])
  }

  const handleToolToggle = (toolId: string) => {
    const currentTools = step.config?.allowedTools || []
    const newTools = currentTools.includes(toolId)
      ? currentTools.filter(t => t !== toolId)
      : [...currentTools, toolId]
    updateConfig({ allowedTools: newTools })
  }

  const resetToolsToDefault = () => {
    updateConfig({ allowedTools: currentTypeConfig.defaultTools })
  }

  // Prompt handlers
  const handlePromptChange = (newPrompt: string) => {
    if (!canEditPrompt) return
    // If the prompt matches the default (normalized), clear customPrompt
    if (!isPromptModified(newPrompt, defaultPrompt)) {
      updateConfig({ customPrompt: undefined })
    } else {
      updateConfig({ customPrompt: newPrompt })
    }
  }

  const handleUseCustomPromptToggle = (useCustom: boolean) => {
    if (!canEditPrompt) return
    if (useCustom) {
      // Copy default prompt to custom
      updateConfig({ customPrompt: defaultPrompt })
    } else {
      // Show reset confirmation
      setShowResetConfirm(true)
    }
  }

  const confirmResetPrompt = () => {
    updateConfig({ customPrompt: undefined })
    setShowResetConfirm(false)
  }

  const isToolInTemplate = (toolId: string) => {
    return currentTypeConfig.defaultTools.includes(toolId)
  }

  const getIcon = (iconType: 'chat' | 'list' | 'code' | 'search') => {
    switch (iconType) {
      case 'chat':
        return (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        )
      case 'list':
        return (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
        )
      case 'search':
        return (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        )
      case 'code':
        return (
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
          </svg>
        )
    }
  }

  return (
    <div className="space-y-6 max-w-2xl">
      {/* Step Name */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Step Name
        </label>
        <input
          type="text"
          value={step.name}
          onChange={(e) => onChange({ ...step, name: e.target.value })}
          className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500"
          placeholder="e.g., Story Generation, Implementation"
        />
      </div>

      {/* Processing Type - Primary Selection */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <label className="block text-sm font-medium text-gray-300">
            What should this step do?
          </label>
          {isProcessingTypeLocked && (
            <span className="text-xs text-amber-400 flex items-center gap-1">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
              Locked after running iterations
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {(Object.entries(PROCESSING_TYPES) as [ProcessingType, ProcessingTypeConfig][]).map(([type, config]) => (
            <button
              key={type}
              type="button"
              onClick={() => handleProcessingTypeClick(type)}
              disabled={isProcessingTypeLocked}
              className={`p-4 rounded-lg border text-left transition-colors ${
                isProcessingTypeLocked
                  ? currentProcessingType === type
                    ? 'bg-gray-800/50 border-gray-600 cursor-not-allowed'
                    : 'bg-gray-800/30 border-gray-700/50 cursor-not-allowed opacity-50'
                  : currentProcessingType === type
                  ? type === 'design_doc'
                    ? 'bg-violet-900/30 border-violet-600'
                    : type === 'extractgen_requirements'
                    ? 'bg-blue-900/30 border-blue-600'
                    : type === 'webgen_requirements'
                    ? 'bg-cyan-900/30 border-cyan-600'
                    : 'bg-emerald-900/30 border-emerald-600'
                  : 'bg-gray-800 border-gray-700 hover:border-gray-600'
              }`}
            >
              <div className={`flex items-center gap-2 mb-2 ${
                isProcessingTypeLocked
                  ? 'text-gray-500'
                  : currentProcessingType === type
                  ? type === 'design_doc'
                    ? 'text-violet-400'
                    : type === 'extractgen_requirements'
                    ? 'text-blue-400'
                    : type === 'webgen_requirements'
                    ? 'text-cyan-400'
                    : 'text-emerald-400'
                  : 'text-gray-400'
              }`}>
                {getIcon(config.icon)}
              </div>
              <div className={`font-medium text-sm mb-1 ${isProcessingTypeLocked ? 'text-gray-400' : 'text-white'}`}>{config.label}</div>
              <p className={`text-xs ${isProcessingTypeLocked ? 'text-gray-600' : currentProcessingType === type ? 'text-gray-300' : 'text-gray-500'}`}>
                {config.description}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Description */}
      <div>
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Description
        </label>
        <textarea
          value={step.config?.description || ''}
          onChange={(e) => updateConfig({ description: e.target.value })}
          className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500 h-20 resize-none"
          placeholder="What does this step do?"
        />
      </div>

      {/* Skippable */}
      <div className="flex items-center space-x-3">
        <input
          type="checkbox"
          id="skippable"
          checked={step.config?.skippable || false}
          onChange={(e) => updateConfig({ skippable: e.target.checked })}
          className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="skippable" className="text-sm text-gray-300">
          Allow skipping this step
        </label>
      </div>

      {/* Design Doc File Selector (for design_doc processing type) */}
      {currentProcessingType === 'design_doc' && (
        <div className="border-t border-gray-700 pt-6">
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Design Document File
          </label>
          <p className="text-xs text-gray-500 mb-3">
            Select an existing design document to edit, or create a new one.
          </p>

          {loadingDesignDocFiles ? (
            <div className="text-sm text-gray-400">Loading files...</div>
          ) : (
            <>
              <select
                value={step.config?.design_doc_path || ''}
                onChange={(e) => {
                  if (e.target.value === '__create__') {
                    setShowCreateFileModal(true)
                  } else {
                    updateConfig({ design_doc_path: e.target.value || undefined })
                  }
                }}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
              >
                <option value="">(Create new during chat)</option>
                <option value="__create__">+ Create New File...</option>
                {designDocFiles.map((file) => (
                  <option key={file.path} value={file.name}>
                    📄 {file.name} ({(file.size / 1024).toFixed(1)} KB)
                  </option>
                ))}
              </select>

              {step.config?.design_doc_path && (
                <div className="mt-3 p-3 bg-violet-900/20 border border-violet-700/50 rounded-lg">
                  <div className="flex items-start gap-2">
                    <svg className="w-4 h-4 text-violet-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div className="text-xs text-violet-300">
                      <strong>Editing existing file:</strong> Changes will save directly to{' '}
                      <code className="bg-violet-900/50 px-1 rounded">.ralphx/resources/design_doc/{step.config.design_doc_path}</code>.
                      Original content will be backed up automatically.
                    </div>
                  </div>
                </div>
              )}

              {!step.config?.design_doc_path && (
                <div className="mt-3 p-3 bg-gray-800/50 border border-gray-700 rounded-lg">
                  <div className="flex items-start gap-2">
                    <svg className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                    <div className="text-xs text-gray-400">
                      <strong>Creating new:</strong> A new design document will be created when you complete this step.
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Create File Modal */}
      {showCreateFileModal && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowCreateFileModal(false)
              setNewFileName('')
            }
          }}
        >
          <div className="bg-gray-800 rounded-xl border border-gray-600 p-6 w-full max-w-md mx-4">
            <h3 className="text-lg font-semibold text-white mb-4">Create New Design Document</h3>

            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-300 mb-2">
                File Name
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={newFileName}
                  onChange={(e) => setNewFileName(e.target.value)}
                  placeholder="e.g., API_DESIGN"
                  className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-primary-500"
                  autoFocus
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleCreateFile()
                    if (e.key === 'Escape') {
                      setShowCreateFileModal(false)
                      setNewFileName('')
                    }
                  }}
                />
                <span className="text-gray-400">.md</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">
                Will be saved to .ralphx/resources/design_doc/
              </p>
            </div>

            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowCreateFileModal(false)
                  setNewFileName('')
                }}
                className="px-4 py-2 bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCreateFile}
                disabled={!newFileName.trim() || creatingFile}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 disabled:opacity-50"
              >
                {creatingFile ? 'Creating...' : 'Create'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Autonomous Step Settings */}
      {step.step_type === 'autonomous' && (
        <div className="border-t border-gray-700 pt-6 space-y-6">
          <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wide">
            Execution Settings
          </h3>

          <div className="grid grid-cols-2 gap-4">
            {/* Model */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                AI Model
              </label>
              <select
                value={step.config?.model || 'opus'}
                onChange={(e) => updateConfig({ model: e.target.value as 'sonnet' | 'opus' | 'haiku' | 'sonnet-1m' })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
              >
                <option value="opus">Opus (Most Capable)</option>
                <option value="sonnet">Sonnet (Balanced)</option>
                <option value="sonnet-1m">Sonnet Extended (1M tokens)</option>
                <option value="haiku">Haiku (Fast)</option>
              </select>
              {step.config?.model === 'sonnet-1m' && (
                <div className="text-amber-400 text-xs mt-2 p-2 bg-amber-900/20 border border-amber-800/50 rounded">
                  <div className="flex items-start gap-1.5">
                    <svg className="w-4 h-4 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>
                      Extended context is not available to all accounts. Only use this if you have already tested <code className="bg-amber-900/50 px-1 rounded">--model sonnet</code> with large contexts in Claude Code and confirmed it works.
                    </span>
                  </div>
                </div>
              )}
            </div>

            {/* Timeout */}
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">
                Timeout (seconds)
              </label>
              <input
                type="number"
                value={step.config?.timeout || 600}
                onChange={(e) => updateConfig({ timeout: parseInt(e.target.value) || 600 })}
                min={60}
                max={7200}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500"
              />
            </div>
          </div>

          {/* Tools - Checkbox List */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm font-medium text-gray-400">
                Available Tools
              </label>
              <button
                type="button"
                onClick={resetToolsToDefault}
                className="text-xs text-primary-400 hover:text-primary-300 flex items-center gap-1"
              >
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Reset to template defaults
              </button>
            </div>
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
              <div className="text-xs text-gray-500 mb-3">
                Template: {currentTypeConfig.label}
              </div>
              <div className="grid grid-cols-2 gap-2">
                {ALL_TOOLS.map(tool => {
                  const isEnabled = (step.config?.allowedTools || []).includes(tool.id)
                  const inTemplate = isToolInTemplate(tool.id)
                  return (
                    <label
                      key={tool.id}
                      className={`flex items-start gap-2 p-2 rounded cursor-pointer hover:bg-gray-700/50 ${
                        isEnabled ? 'text-white' : 'text-gray-500'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isEnabled}
                        onChange={() => handleToolToggle(tool.id)}
                        className="mt-0.5 w-4 h-4 rounded border-gray-600 bg-gray-700 text-primary-600 focus:ring-primary-500"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium flex items-center gap-1">
                          {tool.label}
                          {inTemplate && (
                            <span className="text-xs text-primary-400" title="In template defaults">*</span>
                          )}
                        </div>
                        <div className="text-xs text-gray-500 truncate">{tool.description}</div>
                      </div>
                    </label>
                  )
                })}
              </div>
            </div>
          </div>

          {/* Loop Limits */}
          <div className="border-t border-gray-700 pt-6">
            <h4 className="text-sm font-medium text-gray-300 mb-4">Run Cycle Limits</h4>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Max Run Cycles
                </label>
                <input
                  type="number"
                  value={step.config?.max_iterations ?? ''}
                  onChange={(e) => updateConfig({
                    max_iterations: e.target.value ? parseInt(e.target.value) : undefined
                  })}
                  placeholder={String(DEFAULTS.max_iterations)}
                  min={0}
                  max={10000}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500 placeholder-gray-500"
                />
                <p className="text-xs text-gray-500 mt-1">Default: {DEFAULTS.max_iterations} (0 = unlimited)</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Cooldown (sec)
                </label>
                <input
                  type="number"
                  value={step.config?.cooldown_between_iterations ?? ''}
                  onChange={(e) => updateConfig({
                    cooldown_between_iterations: e.target.value ? parseInt(e.target.value) : undefined
                  })}
                  placeholder={String(DEFAULTS.cooldown_between_iterations)}
                  min={0}
                  max={300}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500 placeholder-gray-500"
                />
                <p className="text-xs text-gray-500 mt-1">Default: {DEFAULTS.cooldown_between_iterations}s</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">
                  Max Errors
                </label>
                <input
                  type="number"
                  value={step.config?.max_consecutive_errors ?? ''}
                  onChange={(e) => updateConfig({
                    max_consecutive_errors: e.target.value ? parseInt(e.target.value) : undefined
                  })}
                  placeholder={String(DEFAULTS.max_consecutive_errors)}
                  min={1}
                  max={100}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:border-primary-500 placeholder-gray-500"
                />
                <p className="text-xs text-gray-500 mt-1">Default: {DEFAULTS.max_consecutive_errors}</p>
              </div>
            </div>
          </div>

          {/* Cross-Step Item Context (for generator steps only) */}
          {(currentProcessingType === 'extractgen_requirements' || currentProcessingType === 'webgen_requirements') && (() => {
            const otherSteps = allSteps.filter(s => s.id && s.id !== step.id)
            const selectedStepIds = step.config?.context_from_steps || []
            if (otherSteps.length === 0) return null
            return (
              <div className="border-t border-gray-700 pt-6">
                <h4 className="text-sm font-medium text-gray-300 mb-2">Context from Other Steps</h4>
                <p className="text-xs text-gray-500 mb-3">
                  Include work items from other steps as context so this step avoids generating duplicates.
                </p>
                <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 space-y-2">
                  {otherSteps.map(s => {
                    const isChecked = selectedStepIds.includes(s.id)
                    const stepTemplate = s.config?.template
                    const typeLabel = stepTemplate === 'extractgen_requirements' ? 'Extract'
                      : stepTemplate === 'webgen_requirements' ? 'WebGen'
                      : stepTemplate === 'implementation' ? 'Impl'
                      : s.step_type === 'interactive' ? 'Design' : 'Step'
                    return (
                      <label
                        key={s.id}
                        className={`flex items-center gap-3 p-2 rounded cursor-pointer hover:bg-gray-700/50 ${
                          isChecked ? 'text-white' : 'text-gray-400'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => {
                            const newIds = isChecked
                              ? selectedStepIds.filter(id => id !== s.id)
                              : [...selectedStepIds, s.id]
                            updateConfig({ context_from_steps: newIds.length > 0 ? newIds : undefined })
                          }}
                          className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-primary-600 focus:ring-primary-500"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium flex items-center gap-2">
                            {s.name}
                            <span className="text-xs px-1.5 py-0.5 bg-gray-700 text-gray-400 rounded">
                              {typeLabel}
                            </span>
                          </div>
                          {s.items_generated ? (
                            <div className="text-xs text-gray-500">{s.items_generated} items</div>
                          ) : null}
                        </div>
                      </label>
                    )
                  })}
                </div>
              </div>
            )
          })()}

          {/* AI Instructions (Advanced) */}
          <div className="border-t border-gray-700 pt-6">
            {/* Collapsible Header */}
            <button
              type="button"
              onClick={() => setPromptExpanded(!promptExpanded)}
              className="w-full flex items-center justify-between text-left"
            >
              <div className="flex items-center gap-2">
                <h4 className="text-sm font-medium text-gray-300">
                  AI Instructions (Advanced)
                </h4>
                {isUsingCustomPrompt && (
                  <span className="px-2 py-0.5 bg-amber-900/30 text-amber-400 text-xs rounded-full">
                    customized
                  </span>
                )}
              </div>
              <svg
                className={`w-5 h-5 text-gray-400 transition-transform ${promptExpanded ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {/* Expanded Content */}
            {promptExpanded && (
              <div className="mt-4 space-y-4">
                {/* Step Running Warning */}
                {isStepRunning && (
                  <div className="p-3 bg-red-900/20 border border-red-800/50 rounded-lg text-red-400 text-sm flex items-start gap-2">
                    <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    <span>Cannot edit while step is running. Stop the step to make changes.</span>
                  </div>
                )}

                {/* Warning Banner */}
                {isUsingCustomPrompt ? (
                  <div className="p-3 bg-amber-900/20 border border-amber-800/50 rounded-lg">
                    <div className="flex items-start gap-2">
                      <svg className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <div className="text-amber-400 text-sm">
                        <strong>ADVANCED:</strong> Editing these instructions can break the step.
                        Only modify if you understand the template variables below.
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="p-3 bg-gray-800/50 border border-gray-700 rounded-lg text-gray-400 text-sm">
                    This is the recommended prompt for {currentProcessingType === 'extractgen_requirements' ? 'Extract Requirements (Story Extraction)' : 'Implementation'} steps.
                  </div>
                )}

                {/* Template Variables Toggle */}
                <div className="flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setShowVariables(!showVariables)}
                    className="text-xs text-primary-400 hover:text-primary-300 flex items-center gap-1"
                  >
                    <svg className={`w-4 h-4 transition-transform ${showVariables ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                    {showVariables ? 'Hide' : 'View'} Template Variables
                  </button>
                </div>

                {/* Template Variables Documentation */}
                {showVariables && (
                  <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-xs">
                    <div className="font-medium text-gray-300 mb-2">Available Template Variables:</div>
                    {loadingPrompt ? (
                      <div className="text-gray-500">Loading...</div>
                    ) : promptVariables.length > 0 ? (
                      <div className="space-y-2">
                        {promptVariables.map((v) => (
                          <div key={v.name} className="flex items-start gap-2">
                            <code className={`px-1.5 py-0.5 rounded font-mono ${v.required ? 'bg-amber-900/30 text-amber-400' : 'bg-gray-800 text-gray-400'}`}>
                              {v.name}
                            </code>
                            <span className="text-gray-500">
                              {v.description}
                              {v.required && <span className="text-amber-400 ml-1">(required)</span>}
                            </span>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-gray-500">No variables available</div>
                    )}
                  </div>
                )}

                {/* Prompt Error State */}
                {promptError && (
                  <div className="p-3 bg-red-900/20 border border-red-800/50 rounded-lg text-red-400 text-sm flex items-center justify-between">
                    <span>{promptError}</span>
                    <button
                      type="button"
                      onClick={fetchDefaultPrompt}
                      className="text-red-300 hover:text-red-200 underline"
                    >
                      Retry
                    </button>
                  </div>
                )}

                {/* Validation Warnings */}
                {isUsingCustomPrompt && validation.warnings.length > 0 && (
                  <div className="p-3 bg-amber-900/20 border border-amber-800/50 rounded-lg text-sm">
                    <div className="font-medium text-amber-400 mb-1 flex items-center gap-1">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
                      </svg>
                      Validation Warnings:
                    </div>
                    <ul className="text-amber-400/80 space-y-1">
                      {validation.warnings.map((w, i) => (
                        <li key={i}>{w}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Prompt Textarea */}
                <div>
                  {loadingPrompt ? (
                    <div className="h-64 bg-gray-800 border border-gray-700 rounded-lg flex items-center justify-center">
                      <div className="text-gray-500">Loading default prompt...</div>
                    </div>
                  ) : (
                    <textarea
                      value={displayedPrompt}
                      onChange={(e) => handlePromptChange(e.target.value)}
                      readOnly={!isUsingCustomPrompt || !canEditPrompt}
                      className={`w-full h-64 px-4 py-3 bg-gray-800 border rounded-lg text-white font-mono text-sm focus:outline-none resize-y ${
                        !isUsingCustomPrompt || !canEditPrompt
                          ? 'border-gray-700 cursor-not-allowed opacity-75'
                          : validation.isValid
                          ? 'border-gray-600 focus:border-primary-500'
                          : 'border-amber-600 focus:border-amber-500'
                      }`}
                      placeholder="AI instructions for this step..."
                    />
                  )}
                </div>

                {/* Action Buttons */}
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={isUsingCustomPrompt}
                      onChange={(e) => handleUseCustomPromptToggle(e.target.checked)}
                      disabled={!canEditPrompt}
                      className="w-4 h-4 rounded border-gray-600 bg-gray-700 text-primary-600 focus:ring-primary-500 disabled:opacity-50"
                    />
                    <span className={`text-sm ${canEditPrompt ? 'text-gray-300' : 'text-gray-500'}`}>
                      Use Custom Instructions
                    </span>
                  </label>

                  {isUsingCustomPrompt && canEditPrompt && (
                    <button
                      type="button"
                      onClick={() => setShowResetConfirm(true)}
                      className="text-sm text-red-400 hover:text-red-300 flex items-center gap-1"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                      </svg>
                      Reset to Default
                    </button>
                  )}
                </div>

                {/* Reset Confirmation Dialog */}
                {showResetConfirm && (
                  <div className="p-4 bg-gray-900 border border-gray-600 rounded-lg">
                    <div className="text-white mb-3">
                      Reset to default instructions?
                    </div>
                    <p className="text-gray-400 text-sm mb-4">
                      This will discard your custom instructions. This action cannot be undone.
                    </p>
                    <div className="flex justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => setShowResetConfirm(false)}
                        className="px-3 py-1.5 text-sm text-gray-400 hover:text-white"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={confirmResetPrompt}
                        className="px-3 py-1.5 text-sm bg-red-600 text-white rounded hover:bg-red-500"
                      >
                        Reset
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Type Change Confirmation Dialog */}
      {showTypeChangeConfirm && pendingTypeChange && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 border border-gray-600 rounded-lg p-6 max-w-md mx-4">
            <h3 className="text-lg font-medium text-white mb-2">
              Change Step Type?
            </h3>
            <p className="text-gray-400 text-sm mb-4">
              Switching to <strong className="text-white">{PROCESSING_TYPES[pendingTypeChange].label}</strong> will reset the following settings to defaults:
            </p>
            <ul className="text-amber-400 text-sm mb-4 list-disc list-inside space-y-1">
              {modifiedFieldsList.map((field, i) => (
                <li key={i}>{field}</li>
              ))}
            </ul>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={cancelTypeChange}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmTypeChange}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500 transition-colors"
              >
                Change Type
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
