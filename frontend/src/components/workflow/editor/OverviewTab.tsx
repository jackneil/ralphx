import { useState, useEffect } from 'react'
import type { Workflow, WorkflowStep, WorkflowResource } from '../../../api'

interface OverviewTabProps {
  workflow: Workflow
  workflowName: string
  onNameChange: (name: string) => void
  steps: WorkflowStep[]
  resources: WorkflowResource[]
  onViewResources?: () => void
}

// Rough token estimation (4 chars per token on average)
function estimateTokens(content: string | undefined): number {
  if (!content) return 0
  return Math.ceil(content.length / 4)
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatTokens(tokens: number): string {
  if (tokens < 1000) return `${tokens}`
  return `${(tokens / 1000).toFixed(1)}k`
}

const resourceTypeConfig: Record<string, { label: string; color: string; icon: JSX.Element }> = {
  design_doc: {
    label: 'Design Doc',
    color: 'text-purple-400 bg-purple-500/10 border-purple-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  guardrail: {
    label: 'Guideline',
    color: 'text-amber-400 bg-amber-500/10 border-amber-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
  },
  input: {
    label: 'Input File',
    color: 'text-blue-400 bg-blue-500/10 border-blue-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
      </svg>
    ),
  },
  prompt: {
    label: 'Prompt',
    color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30',
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    ),
  },
}

export default function OverviewTab({
  workflow: _workflow,
  workflowName,
  onNameChange,
  steps,
  resources,
  onViewResources,
}: OverviewTabProps) {
  const [previewResource, setPreviewResource] = useState<WorkflowResource | null>(null)

  // Handle Escape key to close modal
  useEffect(() => {
    if (!previewResource) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setPreviewResource(null)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [previewResource])

  // Calculate totals
  const totalBytes = resources.reduce((sum, r) => sum + (r.content?.length ?? 0), 0)
  const totalTokens = resources.reduce((sum, r) => sum + estimateTokens(r.content), 0)
  const enabledResources = resources.filter(r => r.enabled)

  // Group by type
  const resourcesByType = resources.reduce((acc, r) => {
    if (!acc[r.resource_type]) acc[r.resource_type] = []
    acc[r.resource_type].push(r)
    return acc
  }, {} as Record<string, WorkflowResource[]>)

  // Context window reference (Claude's context is ~200k tokens)
  const contextUsagePercent = Math.min((totalTokens / 200000) * 100, 100)

  // Check actual resources instead of stale workflow flag
  const hasDesignDoc = resources.some(r => r.resource_type === 'design_doc' && r.enabled)

  return (
    <div className="max-w-3xl space-y-6">
      {/* Workflow Name */}
      <div className="card">
        <label className="block text-sm font-medium text-gray-300 mb-2">
          Workflow Name
        </label>
        <input
          type="text"
          value={workflowName}
          onChange={(e) => onNameChange(e.target.value)}
          className="w-full px-4 py-3 bg-gray-800 border border-gray-600 rounded-lg text-white text-lg placeholder-gray-500 focus:outline-none focus:border-primary-500"
          placeholder="Enter workflow name"
        />
        <p className="mt-2 text-xs text-gray-500">
          Give your workflow a clear, descriptive name that reflects its purpose.
        </p>
      </div>

      {/* Resource Summary */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium text-gray-300">Resources</h3>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">
              {enabledResources.length} of {resources.length} enabled
            </span>
            {onViewResources && (
              <button
                onClick={onViewResources}
                className="text-xs text-primary-400 hover:text-primary-300"
              >
                Manage →
              </button>
            )}
          </div>
        </div>

        {resources.length === 0 ? (
          <div className="text-center py-6">
            <svg className="w-10 h-10 mx-auto text-gray-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            <p className="text-sm text-gray-500">No resources attached</p>
            {onViewResources ? (
              <button
                onClick={onViewResources}
                className="text-xs text-primary-400 hover:text-primary-300 mt-2"
              >
                + Add resources
              </button>
            ) : (
              <p className="text-xs text-gray-600 mt-1">Add resources in the Resources tab</p>
            )}
          </div>
        ) : (
          <>
            {/* Token Usage Bar */}
            <div className="mb-4">
              <div className="flex items-center justify-between text-xs text-gray-400 mb-1">
                <span>Context Usage</span>
                <span>{formatTokens(totalTokens)} tokens ({formatBytes(totalBytes)})</span>
              </div>
              <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    contextUsagePercent > 75
                      ? 'bg-red-500'
                      : contextUsagePercent > 50
                      ? 'bg-amber-500'
                      : 'bg-emerald-500'
                  }`}
                  style={{ width: `${Math.max(contextUsagePercent, 1)}%` }}
                />
              </div>
              <div className="flex items-center justify-between text-xs text-gray-500 mt-1">
                <span>{contextUsagePercent.toFixed(1)}% of ~200k context</span>
                {contextUsagePercent > 50 && (
                  <span className="text-amber-400">Consider trimming resources</span>
                )}
              </div>
            </div>

            {/* Resource List by Type */}
            <div className="space-y-3">
              {Object.entries(resourcesByType).map(([type, typeResources]) => {
                const config = resourceTypeConfig[type] || {
                  label: type,
                  color: 'text-gray-400 bg-gray-500/10 border-gray-500/30',
                  icon: <span className="w-4 h-4">📄</span>,
                }
                const typeTokens = typeResources.reduce((sum, r) => sum + estimateTokens(r.content), 0)

                return (
                  <div key={type} className="rounded-lg bg-gray-800/50 border border-gray-700 p-3">
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <span className={`p-1.5 rounded border ${config.color}`}>
                          {config.icon}
                        </span>
                        <span className="text-sm font-medium text-gray-300">
                          {config.label}
                        </span>
                        <span className="text-xs text-gray-500">
                          ({typeResources.length})
                        </span>
                      </div>
                      <span className="text-xs text-gray-500">
                        ~{formatTokens(typeTokens)} tokens
                      </span>
                    </div>

                    <div className="space-y-1">
                      {typeResources.map((resource) => {
                        const tokens = estimateTokens(resource.content)
                        return (
                          <button
                            key={resource.id}
                            onClick={() => setPreviewResource(resource)}
                            className={`w-full flex items-center justify-between text-xs py-1.5 px-2 rounded hover:bg-gray-700/50 transition-colors ${
                              resource.enabled ? 'text-gray-300' : 'text-gray-500 opacity-60'
                            }`}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              {!resource.enabled && (
                                <span className="text-gray-600" title="Disabled">●</span>
                              )}
                              <span className="truncate text-left">{resource.name}</span>
                            </div>
                            <span className="text-gray-500 flex-shrink-0 ml-2">
                              {formatTokens(tokens)} tok
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* Step Progress */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Step Progress</h3>

        {steps.length === 0 ? (
          <p className="text-sm text-gray-500">No steps configured</p>
        ) : (
          <div className="space-y-2">
            {steps.map((step) => {
              const hasTarget = step.iterations_target != null
              const completed = step.iterations_completed ?? 0
              const target = step.iterations_target ?? 0
              const progressPercent = hasTarget && target > 0 ? Math.min((completed / target) * 100, 100) : 0
              const isRunning = step.has_active_run

              return (
                <div key={step.id} className="rounded-lg bg-gray-800/50 border border-gray-700 p-3">
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-gray-500">{step.step_number}.</span>
                      <span className="text-sm text-gray-300">{step.name}</span>
                      <span className={`text-xs px-1.5 py-0.5 rounded ${
                        step.step_type === 'autonomous'
                          ? 'bg-blue-500/20 text-blue-400'
                          : 'bg-purple-500/20 text-purple-400'
                      }`}>
                        {step.step_type === 'autonomous' ? 'Auto' : 'Chat'}
                      </span>
                      {isRunning && (
                        <span className="flex items-center gap-1 text-xs text-emerald-400">
                          <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                          Running
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Progress display */}
                  <div className="flex items-center gap-2 text-xs">
                    {hasTarget ? (
                      <>
                        <div className="flex-1 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                          <div
                            className={`h-full transition-all ${
                              progressPercent >= 100 ? 'bg-emerald-500' : 'bg-blue-500'
                            }`}
                            style={{ width: `${progressPercent}%` }}
                          />
                        </div>
                        <span className="text-gray-400">
                          {completed} / {target}
                        </span>
                      </>
                    ) : (
                      <span className="text-gray-500">
                        {completed > 0 ? `${completed} cycles completed` : 'Not started'}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Configuration Checklist */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Configuration</h3>
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              {hasDesignDoc ? (
                <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              )}
              <span className="text-gray-300">Design Document</span>
            </div>
            <span className={`text-sm ${hasDesignDoc ? 'text-emerald-400' : 'text-amber-400'}`}>
              {hasDesignDoc ? 'Added' : 'Missing'}
            </span>
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              {steps.length > 0 ? (
                <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ) : (
                <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              )}
              <span className="text-gray-300">Steps</span>
            </div>
            <span className={`text-sm ${steps.length > 0 ? 'text-emerald-400' : 'text-amber-400'}`}>
              {steps.length > 0 ? `${steps.length} configured` : 'None'}
            </span>
          </div>
        </div>
      </div>

      {/* Help Text */}
      <div className="rounded-lg bg-gray-800/50 border border-gray-700 p-4">
        <h3 className="text-sm font-medium text-gray-300 mb-2">Getting Started</h3>
        <ul className="text-sm text-gray-400 space-y-2">
          <li className="flex items-start space-x-2">
            <span className="text-primary-400">1.</span>
            <span>Add a <strong>Design Document</strong> in the Resources tab to guide Claude's work</span>
          </li>
          <li className="flex items-start space-x-2">
            <span className="text-primary-400">2.</span>
            <span>Configure your <strong>Steps</strong> - use Chat steps for planning and Automated steps for execution</span>
          </li>
          <li className="flex items-start space-x-2">
            <span className="text-primary-400">3.</span>
            <span>Add <strong>Guidelines</strong> to set boundaries and coding standards</span>
          </li>
          <li className="flex items-start space-x-2">
            <span className="text-primary-400">4.</span>
            <span>Save your changes and return to the workflow to start execution</span>
          </li>
        </ul>
      </div>

      {/* Resource Preview Modal */}
      {previewResource && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50"
          onClick={(e) => {
            // Close when clicking the backdrop
            if (e.target === e.currentTarget) {
              setPreviewResource(null)
            }
          }}
        >
          <div className="bg-gray-800 rounded-xl border border-gray-600 w-full max-w-3xl mx-4 max-h-[80vh] flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-700">
              <div>
                <h3 className="text-lg font-semibold text-white">{previewResource.name}</h3>
                <p className="text-xs text-gray-400 mt-0.5">
                  {resourceTypeConfig[previewResource.resource_type]?.label || previewResource.resource_type}
                  {' • '}
                  {formatTokens(estimateTokens(previewResource.content))} tokens
                  {!previewResource.enabled && ' • Disabled'}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {onViewResources && (
                  <button
                    onClick={() => {
                      setPreviewResource(null)
                      onViewResources()
                    }}
                    className="px-3 py-1.5 text-sm bg-gray-700 text-gray-300 rounded-lg hover:bg-gray-600"
                  >
                    Edit
                  </button>
                )}
                <button
                  onClick={() => setPreviewResource(null)}
                  className="p-1.5 text-gray-400 hover:text-white rounded-lg hover:bg-gray-700"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-4">
              {previewResource.content ? (
                <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono leading-relaxed">
                  {previewResource.content}
                </pre>
              ) : (
                <p className="text-gray-500 text-center py-8">No content</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
