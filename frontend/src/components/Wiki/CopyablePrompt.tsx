import { useState } from 'react'

interface CopyablePromptProps {
  title: string
  description?: string
  prompt: string
  variant?: 'primary' | 'secondary'
}

export default function CopyablePrompt({
  title,
  description,
  prompt,
  variant = 'primary'
}: CopyablePromptProps) {
  const [copied, setCopied] = useState(false)
  const [showDetails, setShowDetails] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(prompt)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const borderColor = variant === 'primary'
    ? 'border-cyan-500/30 hover:border-cyan-500/50'
    : 'border-violet-500/30 hover:border-violet-500/50'

  const headerBg = variant === 'primary'
    ? 'bg-cyan-500/10'
    : 'bg-violet-500/10'

  return (
    <div className={`rounded-lg border ${borderColor} overflow-hidden transition-colors`}>
      {/* Header */}
      <div className={`${headerBg} px-4 py-3 flex items-center justify-between`}>
        <div className="flex items-center space-x-2">
          <svg
            className="w-4 h-4 text-cyan-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
          <span className="text-sm font-medium text-gray-200">{title}</span>
        </div>
        <button
          onClick={handleCopy}
          className={`flex items-center space-x-1.5 px-3 py-1.5 rounded text-xs font-medium transition-all ${
            copied
              ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              : 'bg-gray-700/50 text-gray-300 hover:bg-gray-600/50 border border-gray-600'
          }`}
        >
          {copied ? (
            <>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              <span>Copied!</span>
            </>
          ) : (
            <>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
              </svg>
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Prompt Content */}
      <div className="bg-gray-900/70 p-4">
        <pre className="text-sm text-gray-300 font-mono whitespace-pre-wrap leading-relaxed">
          {prompt}
        </pre>
      </div>

      {/* Description (expandable) */}
      {description && (
        <div className="border-t border-gray-700/50">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="w-full px-4 py-2 flex items-center justify-between text-xs text-gray-500 hover:text-gray-400 hover:bg-gray-800/30 transition-colors"
          >
            <span>What this does</span>
            <svg
              className={`w-4 h-4 transition-transform ${showDetails ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>
          {showDetails && (
            <div className="px-4 pb-3 text-sm text-gray-400">
              {description}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
