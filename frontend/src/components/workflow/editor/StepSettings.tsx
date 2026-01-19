import type { WorkflowStep } from '../../../api'

// Processing type definitions with their associated settings
type ProcessingType = 'design_doc' | 'generator' | 'consumer'

interface ProcessingTypeConfig {
  label: string
  description: string
  icon: 'chat' | 'list' | 'code'
  step_type: 'interactive' | 'autonomous'
  loopType: string
  defaultTools: string[]
}

const PROCESSING_TYPES: Record<ProcessingType, ProcessingTypeConfig> = {
  design_doc: {
    label: 'Build Design Doc',
    description: 'Interactive chat to create a PRD or design document',
    icon: 'chat',
    step_type: 'interactive',
    loopType: 'design_doc',
    defaultTools: [],
  },
  generator: {
    label: 'Generate User Stories',
    description: 'Extracts user stories from design documents automatically',
    icon: 'list',
    step_type: 'autonomous',
    loopType: 'generator',
    defaultTools: ['WebSearch', 'WebFetch'],
  },
  consumer: {
    label: 'Implementation',
    description: 'Consumes stories and commits code to git',
    icon: 'code',
    step_type: 'autonomous',
    loopType: 'consumer',
    defaultTools: ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep'],
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
  if (loopType === 'design_doc' || step.step_type === 'interactive') return 'design_doc'
  if (loopType === 'generator' || loopType === 'planning') return 'generator'
  return 'consumer' // implementation, consumer, or default
}

interface StepSettingsProps {
  step: WorkflowStep
  onChange: (step: WorkflowStep) => void
}

export default function StepSettings({ step, onChange }: StepSettingsProps) {
  const currentProcessingType = getProcessingType(step)
  const currentTypeConfig = PROCESSING_TYPES[currentProcessingType]

  // Lock processing type if any iterations have been run
  const hasIterations = (step.iterations_completed || 0) > 0 || (step.items_generated || 0) > 0
  const isProcessingTypeLocked = hasIterations

  const updateConfig = (updates: Partial<NonNullable<WorkflowStep['config']>>) => {
    onChange({
      ...step,
      config: {
        ...step.config,
        ...updates,
      },
    })
  }

  const handleProcessingTypeChange = (type: ProcessingType) => {
    const config = PROCESSING_TYPES[type]
    onChange({
      ...step,
      step_type: config.step_type,
      config: {
        ...step.config,
        loopType: config.loopType,
        // Set default tools for the new type
        allowedTools: config.defaultTools,
      },
    })
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

  const isToolInTemplate = (toolId: string) => {
    return currentTypeConfig.defaultTools.includes(toolId)
  }

  const getIcon = (iconType: 'chat' | 'list' | 'code') => {
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
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {(Object.entries(PROCESSING_TYPES) as [ProcessingType, ProcessingTypeConfig][]).map(([type, config]) => (
            <button
              key={type}
              type="button"
              onClick={() => !isProcessingTypeLocked && handleProcessingTypeChange(type)}
              disabled={isProcessingTypeLocked}
              className={`p-4 rounded-lg border text-left transition-colors ${
                isProcessingTypeLocked
                  ? currentProcessingType === type
                    ? 'bg-gray-800/50 border-gray-600 cursor-not-allowed'
                    : 'bg-gray-800/30 border-gray-700/50 cursor-not-allowed opacity-50'
                  : currentProcessingType === type
                  ? type === 'design_doc'
                    ? 'bg-violet-900/30 border-violet-600'
                    : type === 'generator'
                    ? 'bg-blue-900/30 border-blue-600'
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
                    : type === 'generator'
                    ? 'text-blue-400'
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
                onChange={(e) => updateConfig({ model: e.target.value })}
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
        </div>
      )}
    </div>
  )
}
