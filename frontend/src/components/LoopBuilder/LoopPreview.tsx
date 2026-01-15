import { useState, useEffect, useCallback } from 'react'
import { previewLoopPrompt, PreviewResponse, ModePreview, listItems, Item } from '../../api'

interface LoopPreviewProps {
  projectSlug: string
  loopName: string
  loopType?: string
}

export default function LoopPreview({ projectSlug, loopName, loopType }: LoopPreviewProps) {
  const [preview, setPreview] = useState<PreviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Preview options
  const [selectedMode, setSelectedMode] = useState<string | null>(null)
  const [includeAnnotations, setIncludeAnnotations] = useState(true)
  const [selectedSampleItem, setSelectedSampleItem] = useState<string | null>(null)

  // Sample items for consumer loops
  const [sampleItems, setSampleItems] = useState<Item[]>([])

  // Expanded sections
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['rendered']))

  // Load sample items for consumer loops
  useEffect(() => {
    if (loopType === 'consumer') {
      listItems(projectSlug, { status: 'pending', limit: 10 })
        .then((result) => setSampleItems(result.items))
        .catch(() => {}) // Ignore errors
    }
  }, [projectSlug, loopType])

  // Load preview
  const loadPreview = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await previewLoopPrompt(projectSlug, loopName, {
        mode: selectedMode || undefined,
        sample_item_id: selectedSampleItem || undefined,
        include_annotations: includeAnnotations,
        use_first_pending: !selectedSampleItem,
      })
      setPreview(result)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load preview')
    } finally {
      setLoading(false)
    }
  }, [projectSlug, loopName, selectedMode, selectedSampleItem, includeAnnotations])

  useEffect(() => {
    loadPreview()
  }, [loadPreview])

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev)
      if (next.has(section)) {
        next.delete(section)
      } else {
        next.add(section)
      }
      return next
    })
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="p-4 bg-red-900/30 border border-red-800 rounded text-red-400">
          {error}
        </div>
        <button
          onClick={loadPreview}
          className="mt-4 px-4 py-2 bg-gray-700 text-white rounded hover:bg-gray-600"
        >
          Retry
        </button>
      </div>
    )
  }

  if (!preview) {
    return null
  }

  return (
    <div className="p-6 space-y-6">
      {/* Preview Controls */}
      <div className="bg-gray-700/50 rounded-lg p-4">
        <h4 className="text-sm font-medium text-gray-300 mb-3">Preview Options</h4>
        <div className="flex flex-wrap gap-4">
          {/* Mode Selector */}
          <div>
            <label className="block text-xs text-gray-400 mb-1">Mode</label>
            <select
              value={selectedMode || ''}
              onChange={(e) => setSelectedMode(e.target.value || null)}
              className="bg-gray-800 text-white text-sm rounded px-3 py-1.5 border border-gray-600"
            >
              <option value="">All Modes</option>
              {preview.modes.map((m) => (
                <option key={m.mode_name} value={m.mode_name}>
                  {m.mode_name}
                </option>
              ))}
            </select>
          </div>

          {/* Sample Item Selector (for consumer loops) */}
          {preview.loop_type === 'consumer' && sampleItems.length > 0 && (
            <div>
              <label className="block text-xs text-gray-400 mb-1">Sample Item</label>
              <select
                value={selectedSampleItem || ''}
                onChange={(e) => setSelectedSampleItem(e.target.value || null)}
                className="bg-gray-800 text-white text-sm rounded px-3 py-1.5 border border-gray-600 max-w-xs"
              >
                <option value="">Auto (first pending)</option>
                {sampleItems.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.content.substring(0, 50)}...
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Annotations Toggle */}
          <div className="flex items-center">
            <label className="flex items-center space-x-2 cursor-pointer">
              <input
                type="checkbox"
                checked={includeAnnotations}
                onChange={(e) => setIncludeAnnotations(e.target.checked)}
                className="rounded bg-gray-800 border-gray-600"
              />
              <span className="text-sm text-gray-300">Show Section Markers</span>
            </label>
          </div>

          <button
            onClick={loadPreview}
            className="ml-auto px-3 py-1.5 bg-primary-600 text-white text-sm rounded hover:bg-primary-500"
          >
            Refresh Preview
          </button>
        </div>
      </div>

      {/* Overview */}
      <div className="bg-gray-700/50 rounded-lg p-4">
        <h4 className="text-sm font-medium text-gray-300 mb-3">Loop Overview</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <div>
            <span className="text-gray-400">Type:</span>
            <span className="ml-2 text-white capitalize">{preview.loop_type}</span>
          </div>
          <div>
            <span className="text-gray-400">Strategy:</span>
            <span className="ml-2 text-white">{preview.mode_selection_strategy.replace('_', ' ')}</span>
          </div>
          <div>
            <span className="text-gray-400">Modes:</span>
            <span className="ml-2 text-white">{preview.modes.length}</span>
          </div>
          <div>
            <span className="text-gray-400">Resources:</span>
            <span className="ml-2 text-white">{preview.resources_used.length}</span>
          </div>
        </div>
        <p className="mt-3 text-sm text-gray-400">{preview.strategy_explanation}</p>
      </div>

      {/* Resources Used */}
      {preview.resources_used.length > 0 && (
        <div className="bg-gray-700/50 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-300 mb-2">Resources Injected</h4>
          <div className="flex flex-wrap gap-2">
            {preview.resources_used.map((resource) => (
              <span
                key={resource}
                className="px-2 py-1 text-xs bg-blue-900/30 text-blue-400 rounded"
              >
                {resource}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Template Variables */}
      {Object.keys(preview.template_variables).length > 0 && (
        <div className="bg-gray-700/50 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-300 mb-2">Template Variables</h4>
          <div className="space-y-1">
            {Object.entries(preview.template_variables).map(([key, value]) => (
              <div key={key} className="flex text-sm">
                <code className="text-yellow-400 font-mono">{key}</code>
                <span className="mx-2 text-gray-500">=</span>
                <span className="text-gray-300 truncate">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Warnings */}
      {preview.warnings.length > 0 && (
        <div className="bg-yellow-900/20 border border-yellow-800/50 rounded-lg p-4">
          <h4 className="text-sm font-medium text-yellow-400 mb-2">Warnings</h4>
          <ul className="list-disc list-inside text-sm text-yellow-300 space-y-1">
            {preview.warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Mode Previews */}
      {preview.modes.map((modePreview) => (
        <ModePreviewCard
          key={modePreview.mode_name}
          modePreview={modePreview}
          expandedSections={expandedSections}
          onToggleSection={toggleSection}
          onCopy={copyToClipboard}
        />
      ))}

      {/* Sample Item Preview */}
      {preview.sample_item && (
        <div className="bg-gray-700/50 rounded-lg p-4">
          <h4 className="text-sm font-medium text-gray-300 mb-2">Sample Item Used</h4>
          <pre className="text-xs text-gray-400 bg-gray-900 p-3 rounded overflow-x-auto">
            {JSON.stringify(preview.sample_item, null, 2)}
          </pre>
        </div>
      )}
    </div>
  )
}

// Mode Preview Card Component
function ModePreviewCard({
  modePreview,
  expandedSections,
  onToggleSection,
  onCopy,
}: {
  modePreview: ModePreview
  expandedSections: Set<string>
  onToggleSection: (section: string) => void
  onCopy: (text: string) => void
}) {
  const sectionKey = `rendered-${modePreview.mode_name}`
  const sectionsKey = `sections-${modePreview.mode_name}`

  return (
    <div className="bg-gray-700/50 rounded-lg overflow-hidden">
      {/* Mode Header */}
      <div className="p-4 border-b border-gray-600">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="text-white font-medium">{modePreview.mode_name}</h4>
            <p className="text-sm text-gray-400">
              Model: {modePreview.model} | Timeout: {modePreview.timeout}s |
              Tools: {modePreview.tools.length > 0 ? modePreview.tools.join(', ') : 'None'}
            </p>
          </div>
          <div className="text-right text-sm">
            <div className="text-gray-300">
              ~{modePreview.token_estimate.toLocaleString()} tokens
            </div>
            <div className="text-gray-500">
              {modePreview.total_length.toLocaleString()} chars
            </div>
          </div>
        </div>

        {/* Mode Warnings */}
        {modePreview.warnings.length > 0 && (
          <div className="mt-2 p-2 bg-yellow-900/20 rounded text-sm text-yellow-400">
            {modePreview.warnings.join(', ')}
          </div>
        )}
      </div>

      {/* Sections Breakdown */}
      <div className="border-b border-gray-600">
        <button
          onClick={() => onToggleSection(sectionsKey)}
          className="w-full px-4 py-2 text-left text-sm text-gray-400 hover:bg-gray-600/30 flex items-center justify-between"
        >
          <span>Section Breakdown ({modePreview.sections.length} sections)</span>
          <svg
            className={`w-4 h-4 transition-transform ${expandedSections.has(sectionsKey) ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {expandedSections.has(sectionsKey) && (
          <div className="px-4 pb-4 space-y-2">
            {modePreview.sections.map((section, i) => (
              <div
                key={i}
                className="p-2 bg-gray-800 rounded text-sm"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-gray-400">
                    [{section.position.toUpperCase()}]
                  </span>
                  <span className="text-xs text-gray-500">
                    {section.source} {section.source_name && `(${section.source_name})`}
                  </span>
                </div>
                <div className="text-xs text-gray-500">
                  Lines {section.start_line}-{section.end_line} | {section.content.length} chars
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Rendered Prompt */}
      <div>
        <button
          onClick={() => onToggleSection(sectionKey)}
          className="w-full px-4 py-2 text-left text-sm text-gray-400 hover:bg-gray-600/30 flex items-center justify-between"
        >
          <span>Rendered Prompt</span>
          <div className="flex items-center space-x-2">
            <button
              onClick={(e) => {
                e.stopPropagation()
                onCopy(modePreview.rendered_prompt)
              }}
              className="text-xs px-2 py-1 bg-gray-600 hover:bg-gray-500 rounded"
            >
              Copy
            </button>
            <svg
              className={`w-4 h-4 transition-transform ${expandedSections.has(sectionKey) ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </button>

        {expandedSections.has(sectionKey) && (
          <div className="p-4">
            <pre className="text-xs text-gray-300 bg-gray-900 p-4 rounded overflow-x-auto whitespace-pre-wrap max-h-96 overflow-y-auto font-mono">
              {modePreview.rendered_prompt}
            </pre>
          </div>
        )}
      </div>
    </div>
  )
}
