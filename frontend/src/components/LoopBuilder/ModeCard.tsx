import { useState } from 'react'
import { ModeConfig } from './types'

interface ModeCardProps {
  mode: ModeConfig
  isExpanded: boolean
  onToggle: () => void
  onChange: (mode: ModeConfig) => void
  onDelete: () => void
}

const MODEL_OPTIONS = [
  { value: 'claude-sonnet-4-20250514', label: 'Claude Sonnet 4' },
  { value: 'claude-opus-4-20250514', label: 'Claude Opus 4' },
  { value: 'claude-3-5-haiku-20241022', label: 'Claude 3.5 Haiku' },
]

export default function ModeCard({
  mode,
  isExpanded,
  onToggle,
  onChange,
  onDelete,
}: ModeCardProps) {
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const handleDelete = () => {
    if (showDeleteConfirm) {
      onDelete()
    } else {
      setShowDeleteConfirm(true)
      setTimeout(() => setShowDeleteConfirm(false), 3000)
    }
  }

  return (
    <div className="border border-gray-600 rounded-lg bg-gray-700/50 overflow-hidden">
      {/* Header */}
      <div
        className="flex items-center justify-between p-3 cursor-pointer hover:bg-gray-700/70 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center space-x-3">
          <svg
            className={`w-5 h-5 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <div>
            <div className="font-medium text-white">
              {mode.name || <span className="text-gray-400 italic">Unnamed mode</span>}
            </div>
            <div className="text-xs text-gray-400">
              {MODEL_OPTIONS.find((m) => m.value === mode.model)?.label || mode.model}
              {' · '}
              {mode.timeout}s timeout
            </div>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation()
            handleDelete()
          }}
          className={`px-2 py-1 text-sm rounded transition-colors ${
            showDeleteConfirm
              ? 'bg-red-800 text-red-200 hover:bg-red-700'
              : 'text-gray-400 hover:text-red-400 hover:bg-gray-600'
          }`}
        >
          {showDeleteConfirm ? 'Confirm Delete' : 'Delete'}
        </button>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="p-4 border-t border-gray-600 space-y-4">
          {/* Mode Name */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Mode Name <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={mode.name}
              onChange={(e) => onChange({ ...mode, name: e.target.value })}
              placeholder="e.g., turbo, deep, default"
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-primary-500 font-mono"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Description
            </label>
            <input
              type="text"
              value={mode.description}
              onChange={(e) => onChange({ ...mode, description: e.target.value })}
              placeholder="Brief description of this mode's purpose"
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
            />
          </div>

          {/* Model & Timeout */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Model
              </label>
              <select
                value={mode.model}
                onChange={(e) => onChange({ ...mode, model: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white focus:outline-none focus:border-primary-500"
              >
                {MODEL_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Timeout (seconds)
              </label>
              <input
                type="number"
                value={mode.timeout}
                onChange={(e) => onChange({ ...mode, timeout: parseInt(e.target.value) || 300 })}
                min={1}
                max={7200}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white focus:outline-none focus:border-primary-500"
              />
            </div>
          </div>

          {/* Prompt Template */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Prompt Template <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={mode.prompt_template}
              onChange={(e) => onChange({ ...mode, prompt_template: e.target.value })}
              placeholder="prompts/research.md"
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-primary-500 font-mono"
            />
            <p className="mt-1 text-xs text-gray-500">
              Path to the prompt template file relative to .ralphx/ directory
            </p>
          </div>

          {/* Tools (optional) */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Tools (optional)
            </label>
            <input
              type="text"
              value={mode.tools.join(', ')}
              onChange={(e) =>
                onChange({
                  ...mode,
                  tools: e.target.value
                    .split(',')
                    .map((t) => t.trim())
                    .filter(Boolean),
                })
              }
              placeholder="read_file, write_file, execute_command"
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
            />
            <p className="mt-1 text-xs text-gray-500">
              Comma-separated list of tool names available to this mode
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
