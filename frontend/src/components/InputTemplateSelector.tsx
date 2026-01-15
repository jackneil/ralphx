import { useState, useEffect } from 'react'
import { listInputTemplates, getInputTemplate, InputTemplateInfo } from '../api'

interface InputTemplateSelectorProps {
  loopType: 'planning' | 'implementation'
  onSelect: (templateId: string) => void
  onCancel: () => void
}

const TAG_LABELS: Record<string, string> = {
  master_design: 'Master Design',
  story_instructions: 'Story Instructions',
  stories: 'Stories (JSONL)',
  guardrails: 'Guardrails',
  reference: 'Reference',
}

export default function InputTemplateSelector({
  loopType,
  onSelect,
  onCancel,
}: InputTemplateSelectorProps) {
  const [templates, setTemplates] = useState<InputTemplateInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<InputTemplateInfo | null>(null)
  const [templateContent, setTemplateContent] = useState<string | null>(null)
  const [loadingContent, setLoadingContent] = useState(false)

  useEffect(() => {
    loadTemplates()
  }, [loopType])

  const loadTemplates = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listInputTemplates(loopType)
      setTemplates(data)
      // Auto-select first template if available
      if (data.length > 0) {
        handleSelectTemplate(data[0])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load templates')
    } finally {
      setLoading(false)
    }
  }

  const handleSelectTemplate = async (template: InputTemplateInfo) => {
    setSelectedTemplate(template)
    setLoadingContent(true)
    try {
      const detail = await getInputTemplate(template.id)
      setTemplateContent(detail.content)
    } catch (err) {
      setTemplateContent('Failed to load template content')
    } finally {
      setLoadingContent(false)
    }
  }

  const handleApply = () => {
    if (selectedTemplate) {
      onSelect(selectedTemplate.id)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg w-full max-w-4xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex justify-between items-center">
          <div>
            <h3 className="text-lg font-semibold text-white">Input Templates</h3>
            <p className="text-sm text-gray-400 mt-1">
              Pre-curated inputs for {loopType} loops
            </p>
          </div>
          <button
            onClick={onCancel}
            className="p-1 text-gray-400 hover:text-white"
            aria-label="Close"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Pane - Template List */}
          <div className="w-1/3 border-r border-gray-700 overflow-y-auto">
            {loading ? (
              <div className="p-4 text-gray-400">Loading templates...</div>
            ) : error ? (
              <div className="p-4 text-red-400">{error}</div>
            ) : templates.length === 0 ? (
              <div className="p-4 text-gray-400">No templates available for {loopType} loops</div>
            ) : (
              <div className="p-2 space-y-2">
                {templates.map((template) => (
                  <button
                    key={template.id}
                    onClick={() => handleSelectTemplate(template)}
                    className={`w-full text-left p-3 rounded transition-colors ${
                      selectedTemplate?.id === template.id
                        ? 'bg-primary-600/30 border border-primary-500'
                        : 'bg-gray-700/50 border border-transparent hover:bg-gray-700'
                    }`}
                  >
                    <div className="font-medium text-white">{template.name}</div>
                    <div className="text-sm text-gray-400 mt-1">{template.description}</div>
                    <div className="mt-2 flex items-center space-x-2">
                      <span className="px-2 py-0.5 text-xs bg-gray-600 rounded">
                        {TAG_LABELS[template.tag] || template.tag}
                      </span>
                      <span className="text-xs text-gray-500">{template.filename}</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Right Pane - Preview */}
          <div className="flex-1 flex flex-col">
            <div className="p-3 border-b border-gray-700">
              <span className="text-sm font-medium text-gray-300">Preview</span>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {loadingContent ? (
                <div className="text-gray-400">Loading...</div>
              ) : templateContent ? (
                <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">
                  {templateContent}
                </pre>
              ) : (
                <div className="text-gray-400">Select a template to preview</div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex justify-end space-x-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={handleApply}
            disabled={!selectedTemplate}
            className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50"
          >
            Apply Template
          </button>
        </div>
      </div>
    </div>
  )
}
