import { useState, useEffect, useRef, useCallback } from 'react'
import { listTemplates, getTemplate, TemplateListItem } from '../../api'

interface TemplateSelectorProps {
  onSelect: (templateConfig: Record<string, unknown>, templateYaml: string) => void
  onClose: () => void
}

const CATEGORY_ICONS: Record<string, string> = {
  discovery: 'M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z', // Search
  execution: 'M13 10V3L4 14h7v7l9-11h-7z', // Lightning bolt
  generation: 'M12 4v16m8-8H4', // Plus
  processing: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4', // Clipboard check
}

const TYPE_COLORS: Record<string, string> = {
  generator: 'bg-green-600',
  consumer: 'bg-blue-600',
  hybrid: 'bg-purple-600',
}

export default function TemplateSelector({ onSelect, onClose }: TemplateSelectorProps) {
  const [templates, setTemplates] = useState<TemplateListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<string | null>(null)
  const [loadingTemplate, setLoadingTemplate] = useState(false)
  const modalRef = useRef<HTMLDivElement>(null)
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  // Handle Escape key to close modal
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      onClose()
    }
  }, [onClose])

  useEffect(() => {
    loadTemplates()
  }, [])

  // Focus trap and keyboard handling
  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    // Focus the close button when modal opens
    closeButtonRef.current?.focus()

    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [handleKeyDown])

  const loadTemplates = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await listTemplates()
      setTemplates(response.templates)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load templates')
    } finally {
      setLoading(false)
    }
  }

  const handleSelectTemplate = async (templateName: string) => {
    try {
      setSelectedTemplate(templateName)
      setLoadingTemplate(true)
      const template = await getTemplate(templateName)
      onSelect(template.config, template.config_yaml)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load template')
      setSelectedTemplate(null)
    } finally {
      setLoadingTemplate(false)
    }
  }

  const handleStartFromScratch = () => {
    onSelect({}, '')
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" role="dialog" aria-modal="true" aria-labelledby="template-selector-title">
      <div ref={modalRef} className="bg-gray-800 rounded-lg w-full max-w-3xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <div>
            <h3 id="template-selector-title" className="text-lg font-semibold text-white">Choose a Template</h3>
            <p className="text-sm text-gray-400">
              Start with a pre-configured template or create from scratch
            </p>
          </div>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            className="text-gray-400 hover:text-white"
            aria-label="Close template selector"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-48" role="status" aria-label="Loading templates">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-500" />
            </div>
          ) : error ? (
            <div className="p-4 bg-red-900/30 border border-red-800 rounded text-red-400" role="alert">
              {error}
              <button
                onClick={loadTemplates}
                className="ml-2 underline hover:no-underline"
              >
                Retry
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Start from scratch card */}
              <button
                onClick={handleStartFromScratch}
                className="p-4 border-2 border-dashed border-gray-600 rounded-lg hover:border-gray-500 hover:bg-gray-700/30 transition-all text-left group"
              >
                <div className="flex items-start space-x-3">
                  <div className="p-2 rounded-lg bg-gray-700 group-hover:bg-gray-600 transition-colors">
                    <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h4 className="font-medium text-white group-hover:text-primary-400 transition-colors">
                      Start from Scratch
                    </h4>
                    <p className="text-sm text-gray-400 mt-1">
                      Create a custom loop configuration with all fields empty
                    </p>
                  </div>
                </div>
              </button>

              {/* Template cards */}
              {templates.map((template) => (
                <button
                  key={template.name}
                  onClick={() => handleSelectTemplate(template.name)}
                  disabled={loadingTemplate}
                  className={`p-4 border border-gray-700 rounded-lg hover:border-gray-500 hover:bg-gray-700/30 transition-all text-left group ${
                    selectedTemplate === template.name ? 'border-primary-500 bg-gray-700/50' : ''
                  } ${loadingTemplate ? 'opacity-50 cursor-not-allowed' : ''}`}
                >
                  <div className="flex items-start space-x-3">
                    <div className="p-2 rounded-lg bg-gray-700 group-hover:bg-gray-600 transition-colors">
                      <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d={CATEGORY_ICONS[template.category] || CATEGORY_ICONS.generation}
                        />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center space-x-2">
                        <h4 className="font-medium text-white group-hover:text-primary-400 transition-colors">
                          {template.display_name}
                        </h4>
                        <span className={`px-2 py-0.5 text-xs rounded ${TYPE_COLORS[template.type] || 'bg-gray-600'} text-white`}>
                          {template.type}
                        </span>
                      </div>
                      <p className="text-sm text-gray-400 mt-1">
                        {template.description}
                      </p>
                      {selectedTemplate === template.name && loadingTemplate && (
                        <div className="mt-2 flex items-center text-sm text-primary-400">
                          <svg className="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          Loading template...
                        </div>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700">
          <p className="text-xs text-gray-500">
            Templates provide pre-configured settings. You can customize all values after selection.
          </p>
        </div>
      </div>
    </div>
  )
}
