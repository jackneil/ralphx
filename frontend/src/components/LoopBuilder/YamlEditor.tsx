import { useState } from 'react'

interface YamlEditorProps {
  content: string
  error: string | null
  onChange: (content: string) => void
}

export default function YamlEditor({ content, error, onChange }: YamlEditorProps) {
  const [copyFeedback, setCopyFeedback] = useState<'idle' | 'copied' | 'failed'>('idle')

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content)
      setCopyFeedback('copied')
      setTimeout(() => setCopyFeedback('idle'), 2000)
    } catch {
      setCopyFeedback('failed')
      setTimeout(() => setCopyFeedback('idle'), 2000)
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Error banner */}
      {error && (
        <div
          id="yaml-error"
          role="alert"
          className="p-3 bg-red-900/30 border-b border-red-800 text-sm text-red-400"
        >
          <div className="flex items-center space-x-2">
            <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        </div>
      )}

      {/* Editor toolbar */}
      <div className="flex items-center justify-between px-4 py-2 bg-gray-700/50 border-b border-gray-700">
        <span className="text-sm text-gray-400">YAML Configuration</span>
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={handleCopy}
            className={`px-2 py-1 text-xs rounded transition-colors ${
              copyFeedback === 'copied'
                ? 'bg-green-700 text-green-200'
                : copyFeedback === 'failed'
                ? 'bg-red-700 text-red-200'
                : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
            }`}
            title="Copy to clipboard"
            aria-live="polite"
          >
            {copyFeedback === 'copied' ? 'Copied!' : copyFeedback === 'failed' ? 'Failed' : 'Copy'}
          </button>
        </div>
      </div>

      {/* Textarea editor */}
      <div className="flex-1 p-4">
        <label htmlFor="yaml-editor" className="sr-only">
          YAML Configuration Editor
        </label>
        <textarea
          id="yaml-editor"
          value={content}
          onChange={(e) => onChange(e.target.value)}
          className={`w-full h-full min-h-[400px] px-4 py-3 bg-gray-900 border rounded font-mono text-sm text-gray-200 focus:outline-none resize-none ${
            error ? 'border-red-600 focus:border-red-500' : 'border-gray-700 focus:border-primary-500'
          }`}
          spellCheck={false}
          placeholder="# Enter your loop configuration in YAML format..."
          aria-invalid={error ? 'true' : 'false'}
          aria-describedby={error ? 'yaml-error' : undefined}
        />
      </div>

      {/* Help section */}
      <div className="p-4 bg-gray-700/30 border-t border-gray-700">
        <div className="text-xs text-gray-500">
          <strong className="text-gray-400">Tip:</strong> Fix any YAML errors before switching to the
          Visual Editor or saving. Valid YAML will automatically sync when you switch tabs.
        </div>
      </div>
    </div>
  )
}
