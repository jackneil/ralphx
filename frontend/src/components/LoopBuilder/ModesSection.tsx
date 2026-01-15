import { useState, useCallback } from 'react'
import { ModeConfig } from './types'
import ModeCard from './ModeCard'

interface ModesSectionProps {
  modes: ModeConfig[]
  onChange: (modes: ModeConfig[]) => void
}

export default function ModesSection({ modes, onChange }: ModesSectionProps) {
  const [expandedIndex, setExpandedIndex] = useState<number | null>(
    modes.length === 0 ? null : 0
  )

  const handleModeChange = useCallback(
    (index: number, mode: ModeConfig) => {
      const newModes = [...modes]
      newModes[index] = mode
      onChange(newModes)
    },
    [modes, onChange]
  )

  const handleDeleteMode = useCallback(
    (index: number) => {
      const newModes = modes.filter((_, i) => i !== index)
      onChange(newModes)
      if (expandedIndex === index) {
        setExpandedIndex(newModes.length > 0 ? 0 : null)
      } else if (expandedIndex !== null && expandedIndex > index) {
        setExpandedIndex(expandedIndex - 1)
      }
    },
    [modes, onChange, expandedIndex]
  )

  const handleAddMode = () => {
    const newMode: ModeConfig = {
      name: `mode_${modes.length + 1}`,
      description: '',
      model: 'claude-sonnet-4-20250514',
      timeout: 300,
      tools: [],
      prompt_template: '',
    }
    onChange([...modes, newMode])
    setExpandedIndex(modes.length)
  }

  return (
    <section>
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
        <span className="w-8 h-8 rounded-full bg-primary-600 text-white flex items-center justify-center text-sm font-bold mr-3">
          3
        </span>
        Modes
      </h3>

      <div className="space-y-3 pl-11">
        <p className="text-sm text-gray-400">
          Modes define different LLM configurations for your loop. Each iteration uses one mode
          based on the selection strategy.
        </p>

        {modes.length === 0 ? (
          <div className="p-4 border-2 border-dashed border-gray-600 rounded-lg text-center">
            <p className="text-gray-400 mb-2">No modes configured</p>
            <p className="text-xs text-gray-500 mb-4">
              At least one mode is required for the loop to run
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {modes.map((mode, index) => (
              <ModeCard
                key={mode.name || `unnamed_mode_${index}`}
                mode={mode}
                isExpanded={expandedIndex === index}
                onToggle={() => setExpandedIndex(expandedIndex === index ? null : index)}
                onChange={(updated) => handleModeChange(index, updated)}
                onDelete={() => handleDeleteMode(index)}
              />
            ))}
          </div>
        )}

        <button
          type="button"
          onClick={handleAddMode}
          className="w-full p-3 border-2 border-dashed border-gray-600 rounded-lg text-gray-400 hover:border-gray-500 hover:text-gray-300 transition-colors flex items-center justify-center space-x-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>Add Mode</span>
        </button>
      </div>
    </section>
  )
}
