import { useState, useEffect } from 'react'
import type { Workflow, WorkflowResource, WorkflowStep, ResourceVersion } from '../../api'
import { listResourceVersions, restoreResourceVersion } from '../../api'
import { formatRelativeTime } from '../../utils/time'

interface WorkflowStatusBarProps {
  workflow: Workflow
  resources: WorkflowResource[]
  projectSlug: string
  workflowId: string
  onResourceUpdate?: (resourceId: number, content: string, expectedUpdatedAt: string) => Promise<void>
}

// Rough token estimation
function estimateTokens(content: string | undefined): number {
  if (!content) return 0
  return Math.ceil(content.length / 4)
}

function formatTokens(tokens: number): string {
  if (tokens < 1000) return `${tokens}`
  return `${(tokens / 1000).toFixed(1)}k`
}

// ============================================================================
// WORKFLOW TYPE DETECTION
// Analyzes step names and configs to determine what kind of workflow this is
// ============================================================================

type WorkflowType =
  | 'new_product'      // PRD → Stories → Implementation
  | 'feature'          // Feature analysis → Implementation
  | 'bug_fix'          // Bug triage → Fix → Verify
  | 'maintenance'      // Dependency updates, tech debt
  | 'support'          // Ticket resolution
  | 'generic'          // Unknown type

interface WorkflowAnalysis {
  type: WorkflowType
  stage: 'discovery' | 'ready' | 'in_progress' | 'finishing' | 'complete'
  generators: WorkflowStep[]
  consumers: WorkflowStep[]
  totalGenerated: number
  totalProcessed: number
  totalToProcess: number
  totalIterations: number
  isRunning: boolean
  runningStep: WorkflowStep | undefined
  lastActivity: string | undefined
  // Contextual metrics based on workflow type
  primaryMetric: { label: string; value: string | number; subtext?: string }
  secondaryMetric?: { label: string; value: string | number; subtext?: string }
  statusMessage: string
  statusDetail: string
  statusColor: string
  dotClass: string
}

function detectWorkflowType(steps: WorkflowStep[]): WorkflowType {
  const stepNames = steps.map(s => s.name.toLowerCase())
  const stepDescriptions = steps.map(s => (s.config?.description || '').toLowerCase())
  const allText = [...stepNames, ...stepDescriptions].join(' ')

  // Helper to check for word boundaries (avoids matching "fix" in "prefix")
  const hasWord = (text: string, word: string): boolean => {
    const regex = new RegExp(`\\b${word}\\b`, 'i')
    return regex.test(text)
  }

  // Check for keywords that indicate workflow type
  // Priority order: most specific patterns first
  if (hasWord(allText, 'story') || hasWord(allText, 'stories') || hasWord(allText, 'prd') || hasWord(allText, 'user stories') || hasWord(allText, 'requirements')) {
    return 'new_product'
  }
  if (hasWord(allText, 'feature') && (hasWord(allText, 'implement') || hasWord(allText, 'build'))) {
    return 'feature'
  }
  if (hasWord(allText, 'bug') || hasWord(allText, 'bugs') || hasWord(allText, 'defect') || hasWord(allText, 'bugfix') || hasWord(allText, 'triage')) {
    return 'bug_fix'
  }
  if (hasWord(allText, 'dependency') || hasWord(allText, 'tech debt') || hasWord(allText, 'maintenance') || hasWord(allText, 'upgrade')) {
    return 'maintenance'
  }
  if (hasWord(allText, 'ticket') || hasWord(allText, 'support') || hasWord(allText, 'customer') || hasWord(allText, 'resolution')) {
    return 'support'
  }

  return 'generic'
}

function getItemNoun(type: WorkflowType, plural: boolean = true): string {
  const nouns: Record<WorkflowType, [string, string]> = {
    new_product: ['story', 'stories'],
    feature: ['task', 'tasks'],
    bug_fix: ['bug', 'bugs'],
    maintenance: ['item', 'items'],
    support: ['ticket', 'tickets'],
    generic: ['item', 'items'],
  }
  return nouns[type][plural ? 1 : 0]
}

function getGeneratorVerb(type: WorkflowType): string {
  const verbs: Record<WorkflowType, string> = {
    new_product: 'discovered',
    feature: 'identified',
    bug_fix: 'triaged',
    maintenance: 'found',
    support: 'received',
    generic: 'generated',
  }
  return verbs[type]
}

function getConsumerVerb(type: WorkflowType): string {
  const verbs: Record<WorkflowType, string> = {
    new_product: 'implemented',
    feature: 'completed',
    bug_fix: 'fixed',
    maintenance: 'addressed',
    support: 'resolved',
    generic: 'processed',
  }
  return verbs[type]
}

function analyzeWorkflow(workflow: Workflow): WorkflowAnalysis {
  const steps = workflow.steps || []
  const type = detectWorkflowType(steps)

  // Find generators and consumers
  const generators = steps.filter(s => s.config?.loopType === 'generator')
  const consumers = steps.filter(s => s.config?.loopType === 'consumer')

  // Calculate totals
  const totalGenerated = generators.reduce((sum, s) => sum + (s.items_generated || 0), 0)
  const totalProcessed = consumers.reduce((sum, s) => sum + (s.input_items?.completed || 0), 0)
  const totalToProcess = consumers.reduce((sum, s) => sum + (s.input_items?.total || 0), 0)
  const totalIterations = steps.reduce((sum, s) => sum + (s.iterations_completed || 0), 0)

  // Running state
  const isRunning = steps.some(s => s.has_active_run)
  const runningStep = steps.find(s => s.has_active_run)

  // Last activity
  const lastActivity = steps
    .map(s => s.completed_at || s.started_at)
    .filter(Boolean)
    .sort()
    .reverse()[0]

  // Determine stage
  let stage: WorkflowAnalysis['stage']
  if (workflow.status === 'completed') {
    stage = 'complete'
  } else if (totalGenerated === 0) {
    stage = 'discovery'
  } else if (totalProcessed === 0 && totalToProcess > 0) {
    stage = 'ready'
  } else if (totalProcessed < totalToProcess) {
    const progress = totalProcessed / totalToProcess
    stage = progress > 0.8 ? 'finishing' : 'in_progress'
  } else if (totalGenerated > 0 && generators.some(g => g.status !== 'completed')) {
    stage = 'discovery' // Still generating
  } else {
    stage = 'complete'
  }

  // Build contextual status message
  const itemNoun = getItemNoun(type)
  const itemNounSingular = getItemNoun(type, false)
  const genVerb = getGeneratorVerb(type)
  const conVerb = getConsumerVerb(type)

  let statusMessage: string
  let statusDetail: string
  let statusColor: string
  let dotClass: string
  let primaryMetric: WorkflowAnalysis['primaryMetric']
  let secondaryMetric: WorkflowAnalysis['secondaryMetric']

  // Running state takes priority
  if (isRunning && runningStep) {
    const runningStepType = runningStep.config?.loopType
    if (runningStepType === 'generator') {
      statusMessage = type === 'new_product' ? 'Discovering' :
                      type === 'bug_fix' ? 'Triaging' :
                      type === 'support' ? 'Processing' :
                      'Generating'
      statusDetail = `${runningStep.name} in progress...`
    } else {
      statusMessage = type === 'new_product' ? 'Building' :
                      type === 'bug_fix' ? 'Fixing' :
                      type === 'support' ? 'Resolving' :
                      'Processing'
      statusDetail = `Working on ${runningStep.name.toLowerCase()}...`
    }
    statusColor = 'text-emerald-400'
    dotClass = 'bg-emerald-400 animate-pulse'
  } else if (workflow.status === 'completed') {
    statusMessage = 'Complete'
    statusDetail = `All ${itemNoun} ${conVerb}`
    statusColor = 'text-blue-400'
    dotClass = 'bg-blue-400'
  } else if (workflow.status === 'draft') {
    statusMessage = 'Ready'
    statusDetail = 'Workflow not started'
    statusColor = 'text-gray-400'
    dotClass = 'bg-gray-500'
  } else {
    // Paused/idle - show what's next
    if (stage === 'discovery') {
      statusMessage = 'Paused'
      statusDetail = totalGenerated > 0
        ? `${totalGenerated} ${itemNoun} ${genVerb} so far`
        : `Ready to discover ${itemNoun}`
      statusColor = 'text-amber-400'
      dotClass = 'bg-amber-400'
    } else if (stage === 'ready') {
      statusMessage = 'Ready to build'
      statusDetail = `${totalToProcess} ${itemNoun} queued for ${type === 'bug_fix' ? 'fixing' : 'implementation'}`
      statusColor = 'text-cyan-400'
      dotClass = 'bg-cyan-400'
    } else if (stage === 'in_progress' || stage === 'finishing') {
      const remaining = totalToProcess - totalProcessed
      const pct = Math.round((totalProcessed / totalToProcess) * 100)
      statusMessage = 'Paused'
      statusDetail = `${remaining} ${remaining === 1 ? itemNounSingular : itemNoun} remaining (${pct}% done)`
      statusColor = 'text-amber-400'
      dotClass = 'bg-amber-400'
    } else {
      statusMessage = 'Idle'
      statusDetail = 'Ready to continue'
      statusColor = 'text-gray-400'
      dotClass = 'bg-gray-500'
    }
  }

  // Build metrics based on workflow type and stage
  if (type === 'new_product' || type === 'feature') {
    primaryMetric = {
      label: totalProcessed > 0 ? `${itemNoun} ${conVerb}` : `${itemNoun} ${genVerb}`,
      value: totalProcessed > 0 ? `${totalProcessed}/${totalToProcess}` : totalGenerated,
      subtext: totalProcessed > 0 && totalToProcess > 0
        ? `${Math.round((totalProcessed / totalToProcess) * 100)}%`
        : undefined
    }
    if (totalGenerated > 0 && totalProcessed === 0) {
      secondaryMetric = {
        label: 'ready to build',
        value: totalToProcess || totalGenerated,
      }
    }
  } else if (type === 'bug_fix') {
    primaryMetric = {
      label: totalProcessed > 0 ? 'bugs fixed' : 'bugs triaged',
      value: totalProcessed > 0 ? `${totalProcessed}/${totalToProcess}` : totalGenerated,
    }
    if (totalToProcess > 0) {
      const remaining = totalToProcess - totalProcessed
      secondaryMetric = {
        label: 'remaining',
        value: remaining,
      }
    }
  } else if (type === 'support') {
    primaryMetric = {
      label: 'tickets resolved',
      value: totalProcessed > 0 ? `${totalProcessed}/${totalToProcess}` : '0',
    }
    if (totalGenerated > 0) {
      secondaryMetric = {
        label: 'received',
        value: totalGenerated,
      }
    }
  } else {
    // Generic
    primaryMetric = {
      label: totalProcessed > 0 ? 'processed' : 'generated',
      value: totalProcessed > 0 ? `${totalProcessed}/${totalToProcess}` : totalGenerated,
    }
  }

  return {
    type,
    stage,
    generators,
    consumers,
    totalGenerated,
    totalProcessed,
    totalToProcess,
    totalIterations,
    isRunning,
    runningStep,
    lastActivity,
    primaryMetric,
    secondaryMetric,
    statusMessage,
    statusDetail,
    statusColor,
    dotClass,
  }
}

// ============================================================================
// COMPONENT
// ============================================================================

export default function WorkflowStatusBar({
  workflow,
  resources,
  projectSlug,
  workflowId,
  onResourceUpdate
}: WorkflowStatusBarProps) {
  const [expandedResource, setExpandedResource] = useState<WorkflowResource | null>(null)
  const [editingResource, setEditingResource] = useState<WorkflowResource | null>(null)
  const [editContent, setEditContent] = useState('')
  const [originalUpdatedAt, setOriginalUpdatedAt] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showSaveConfirm, setShowSaveConfirm] = useState(false)
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'error' } | null>(null)
  const [viewingVersions, setViewingVersions] = useState<WorkflowResource | null>(null)
  const [versions, setVersions] = useState<ResourceVersion[]>([])
  const [versionsTotal, setVersionsTotal] = useState(0)
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [previewVersion, setPreviewVersion] = useState<ResourceVersion | null>(null)
  const [restoringVersion, setRestoringVersion] = useState(false)

  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 3000)
      return () => clearTimeout(timer)
    }
  }, [toast])

  const analysis = analyzeWorkflow(workflow)

  const enabledResources = resources.filter(r => r.enabled)
  const designDocs = enabledResources.filter(r => r.resource_type === 'design_doc')
  const guidelines = enabledResources.filter(r => r.resource_type === 'guardrail')
  const inputs = enabledResources.filter(r => r.resource_type === 'input_file' || r.resource_type === 'input')
  const prompts = enabledResources.filter(r => r.resource_type === 'prompt')

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
  }

  const handleEditClick = (resource: WorkflowResource, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingResource(resource)
    setEditContent(resource.content || '')
    setOriginalUpdatedAt(resource.updated_at)
    setSaveError(null)
    setExpandedResource(null)
  }

  const handleSaveClick = () => setShowSaveConfirm(true)

  const handleConfirmSave = async () => {
    if (!editingResource || !onResourceUpdate) return
    setSaving(true)
    setSaveError(null)
    setShowSaveConfirm(false)
    try {
      await onResourceUpdate(editingResource.id, editContent, originalUpdatedAt)
      setToast({ message: 'Version saved', type: 'success' })
      setEditingResource(null)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to save'
      if (message.includes('modified in another session') || message.includes('409')) {
        setSaveError('Resource was modified in another session. Please reload.')
      } else {
        setSaveError(message)
      }
    } finally {
      setSaving(false)
    }
  }

  const handleViewHistory = async (resource: WorkflowResource, e: React.MouseEvent) => {
    e.stopPropagation()
    setViewingVersions(resource)
    setVersionsLoading(true)
    setPreviewVersion(null)
    setExpandedResource(null)
    try {
      const data = await listResourceVersions(projectSlug, workflowId, resource.id)
      setVersions(data.versions)
      setVersionsTotal(data.total)
    } catch (err) {
      console.error('Failed to load versions:', err)
      setVersions([])
      setVersionsTotal(0)
    } finally {
      setVersionsLoading(false)
    }
  }

  const handleRestoreVersion = async (version: ResourceVersion) => {
    if (!viewingVersions) return
    setRestoringVersion(true)
    try {
      await restoreResourceVersion(projectSlug, workflowId, viewingVersions.id, version.id)
      setToast({ message: 'Version restored', type: 'success' })
      setViewingVersions(null)
      setPreviewVersion(null)
    } catch (err) {
      console.error('Failed to restore version:', err)
      setToast({ message: 'Failed to restore version', type: 'error' })
    } finally {
      setRestoringVersion(false)
    }
  }

  // Resource card component
  const ResourceCard = ({
    resources: categoryResources,
    label,
    colorClass,
    icon
  }: {
    resources: WorkflowResource[]
    label: string
    colorClass: string
    icon: React.ReactNode
  }) => {
    if (categoryResources.length === 0) return null
    const tokens = categoryResources.reduce((s, r) => s + estimateTokens(r.content), 0)
    const isExpanded = expandedResource && categoryResources.some(r => r.id === expandedResource.id)

    return (
      <div className="relative">
        <button
          onClick={() => setExpandedResource(isExpanded ? null : categoryResources[0])}
          className={`flex items-center gap-3 px-4 py-3 rounded-lg border transition-all hover:border-[var(--color-border-bright)] ${
            isExpanded ? 'border-[var(--color-border-bright)] bg-[var(--color-elevated)]' : 'border-[var(--color-border)] bg-[var(--color-surface)]'
          }`}
        >
          <span className={colorClass}>{icon}</span>
          <div className="text-left">
            <div className="text-sm font-medium text-[var(--color-text-primary)]">
              {categoryResources.length === 1 ? categoryResources[0].name : label}
            </div>
            <div className="text-xs text-[var(--color-text-muted)] flex items-center gap-2">
              {categoryResources.length > 1 && <span>{categoryResources.length} files</span>}
              <span>{formatTokens(tokens)} tokens</span>
            </div>
          </div>
          <svg
            className={`w-4 h-4 text-[var(--color-text-muted)] transition-transform ml-2 ${isExpanded ? 'rotate-180' : ''}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {isExpanded && (
          <div className="absolute top-full left-0 mt-2 w-96 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg shadow-xl z-20 max-h-[400px] overflow-hidden">
            {categoryResources.map((resource) => (
              <div key={resource.id} className="border-b border-[var(--color-border)] last:border-b-0">
                <div className="p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-[var(--color-text-primary)]">{resource.name}</span>
                    <div className="flex items-center gap-1">
                      {onResourceUpdate && (
                        <button
                          onClick={(e) => handleEditClick(resource, e)}
                          className="px-2 py-0.5 text-[10px] text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 rounded"
                        >
                          Edit
                        </button>
                      )}
                      <button
                        onClick={(e) => handleViewHistory(resource, e)}
                        className="px-2 py-0.5 text-[10px] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] rounded"
                      >
                        History
                      </button>
                    </div>
                  </div>
                  <pre className="text-[10px] text-[var(--color-text-muted)] whitespace-pre-wrap font-mono bg-[var(--color-deep)] p-2 rounded max-h-[150px] overflow-y-auto">
                    {(resource.content || '').slice(0, 800)}{(resource.content?.length || 0) > 800 ? '...' : ''}
                  </pre>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <>
      {/* Status Summary Bar */}
      <div className="card-panel mb-4">
        <div className="flex items-center justify-between px-5 py-4">
          {/* Activity Status - contextual message */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${analysis.dotClass}`} />
              <span className={`text-sm font-semibold ${analysis.statusColor}`}>{analysis.statusMessage}</span>
            </div>
            <span className="text-sm text-[var(--color-text-secondary)]">{analysis.statusDetail}</span>
            {analysis.lastActivity && (
              <span className="text-xs text-[var(--color-text-muted)] border-l border-[var(--color-border)] pl-4">
                Last: {formatRelativeTime(analysis.lastActivity, 'Never')}
              </span>
            )}
          </div>

          {/* Contextual Metrics */}
          <div className="flex items-center gap-6">
            <div className="text-right">
              <div className="text-xl font-bold text-[var(--color-text-primary)] font-mono">
                {analysis.primaryMetric.value}
                {analysis.primaryMetric.subtext && (
                  <span className="text-sm text-[var(--color-text-muted)] ml-1">{analysis.primaryMetric.subtext}</span>
                )}
              </div>
              <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">
                {analysis.primaryMetric.label}
              </div>
            </div>
            {analysis.secondaryMetric && (
              <div className="text-right">
                <div className="text-xl font-bold text-[var(--color-text-primary)] font-mono">
                  {analysis.secondaryMetric.value}
                </div>
                <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">
                  {analysis.secondaryMetric.label}
                </div>
              </div>
            )}
            {analysis.totalIterations > 0 && (
              <div className="text-right border-l border-[var(--color-border)] pl-6">
                <div className="text-lg font-bold text-[var(--color-text-secondary)] font-mono">
                  {analysis.totalIterations}
                </div>
                <div className="text-[10px] text-[var(--color-text-muted)] uppercase tracking-wider">
                  cycles
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Progress bar if there's work in progress */}
        {analysis.totalToProcess > 0 && (
          <div className="h-1 bg-[var(--color-border)]">
            <div
              className="h-full bg-gradient-to-r from-cyan-500 to-emerald-500 transition-all duration-500"
              style={{ width: `${(analysis.totalProcessed / analysis.totalToProcess) * 100}%` }}
            />
          </div>
        )}
      </div>

      {/* Resources Row */}
      {enabledResources.length > 0 && (
        <div className="mb-6">
          <div className="text-xs font-semibold text-[var(--color-text-muted)] uppercase tracking-wider mb-3">
            Resources
          </div>
          <div className="flex flex-wrap gap-3">
            <ResourceCard
              resources={designDocs}
              label="Design Docs"
              colorClass="text-purple-400"
              icon={<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>}
            />
            <ResourceCard
              resources={guidelines}
              label="Guidelines"
              colorClass="text-amber-400"
              icon={<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>}
            />
            <ResourceCard
              resources={inputs}
              label="Inputs"
              colorClass="text-blue-400"
              icon={<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" /></svg>}
            />
            <ResourceCard
              resources={prompts}
              label="Prompts"
              colorClass="text-emerald-400"
              icon={<svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" /></svg>}
            />
          </div>
        </div>
      )}

      {/* Click outside to close dropdown */}
      {expandedResource && (
        <div className="fixed inset-0 z-10" onClick={() => setExpandedResource(null)} />
      )}

      {/* Edit Modal */}
      {editingResource && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg w-full max-w-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
              <h3 className="text-lg font-medium text-[var(--color-text-primary)]">Edit: {editingResource.name}</h3>
              <button onClick={() => setEditingResource(null)} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="p-4 flex-1 overflow-auto">
              {saveError && <div className="mb-4 p-3 rounded bg-red-900/20 border border-red-800 text-red-400 text-sm">{saveError}</div>}
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full h-[300px] p-3 bg-[var(--color-elevated)] border border-[var(--color-border)] rounded text-sm text-[var(--color-text-primary)] font-mono resize-none focus:outline-none focus:border-cyan-500"
              />
            </div>
            <div className="flex items-center justify-end gap-3 px-4 py-3 border-t border-[var(--color-border)]">
              <button onClick={() => setEditingResource(null)} className="px-4 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">Cancel</button>
              <button
                onClick={handleSaveClick}
                disabled={saving || editContent === (editingResource.content || '')}
                className="px-4 py-2 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Save Confirmation */}
      {showSaveConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-6 max-w-md">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-amber-500/20 flex items-center justify-center">
                <svg className="w-5 h-5 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h3 className="text-lg font-medium text-[var(--color-text-primary)]">Save Changes?</h3>
            </div>
            <p className="text-sm text-[var(--color-text-secondary)] mb-6">
              This will update the resource for <strong>ALL steps</strong> in this workflow.
            </p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowSaveConfirm(false)} className="px-4 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">Cancel</button>
              <button onClick={handleConfirmSave} disabled={saving} className="px-4 py-2 text-sm bg-cyan-600 text-white rounded hover:bg-cyan-500 disabled:opacity-50">
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Version History Modal */}
      {viewingVersions && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)]">
              <h3 className="text-lg font-medium text-[var(--color-text-primary)]">History: {viewingVersions.name}</h3>
              <button onClick={() => { setViewingVersions(null); setPreviewVersion(null); }} className="text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {versionsLoading ? (
                <div className="text-center py-8 text-[var(--color-text-muted)]">Loading...</div>
              ) : versions.length === 0 ? (
                <div className="text-center py-8 text-[var(--color-text-muted)]">No history yet.</div>
              ) : (
                <div className="space-y-3">
                  {versions.map((version) => (
                    <div key={version.id} className={`p-3 rounded border ${previewVersion?.id === version.id ? 'border-cyan-500 bg-cyan-500/10' : 'border-[var(--color-border)] hover:border-[var(--color-border-bright)]'}`}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-sm font-medium text-[var(--color-text-primary)]">Version {version.version_number}</span>
                        <span className="text-xs text-[var(--color-text-muted)]">{formatDate(version.created_at)}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <button onClick={() => setPreviewVersion(previewVersion?.id === version.id ? null : version)} className="px-2 py-1 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] hover:bg-[var(--color-elevated)] rounded">
                          {previewVersion?.id === version.id ? 'Hide' : 'Preview'}
                        </button>
                        <button onClick={() => handleRestoreVersion(version)} disabled={restoringVersion} className="px-2 py-1 text-xs text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 rounded disabled:opacity-50">
                          {restoringVersion ? 'Restoring...' : 'Restore'}
                        </button>
                      </div>
                      {previewVersion?.id === version.id && (
                        <pre className="mt-3 text-xs text-[var(--color-text-secondary)] whitespace-pre-wrap font-mono bg-[var(--color-elevated)] p-3 rounded max-h-[200px] overflow-y-auto">
                          {version.content || '(empty)'}
                        </pre>
                      )}
                    </div>
                  ))}
                  {versionsTotal > versions.length && (
                    <div className="text-center text-xs text-[var(--color-text-muted)] py-2">
                      Showing {versions.length} of {versionsTotal}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-6 right-6 px-4 py-3 rounded-lg shadow-lg ${toast.type === 'success' ? 'bg-green-900/90 border border-green-700 text-green-400' : 'bg-red-900/90 border border-red-700 text-red-400'}`}>
          {toast.message}
        </div>
      )}
    </>
  )
}
