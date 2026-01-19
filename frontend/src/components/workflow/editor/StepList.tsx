import type { WorkflowStep } from '../../../api'

interface StepListProps {
  steps: WorkflowStep[]
  selectedIndex: number | null
  onSelect: (index: number) => void
  onAdd: () => void
  onMove: (index: number, direction: 'up' | 'down') => void
}

export default function StepList({
  steps,
  selectedIndex,
  onSelect,
  onAdd,
  onMove,
}: StepListProps) {
  const getStepTypeLabel = (stepType: string) => {
    return stepType === 'interactive' ? 'Chat' : 'Automated'
  }

  const getStepTypeColor = (stepType: string) => {
    return stepType === 'interactive'
      ? 'bg-violet-900/50 text-violet-400 border-violet-700/50'
      : 'bg-emerald-900/50 text-emerald-400 border-emerald-700/50'
  }

  const getStatusIndicator = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="w-2 h-2 rounded-full bg-green-400" title="Completed" />
      case 'active':
        return <span className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" title="Active" />
      case 'pending':
      default:
        return <span className="w-2 h-2 rounded-full bg-gray-500" title="Pending" />
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-300 uppercase tracking-wide">Steps</h3>
        <button
          onClick={onAdd}
          className="p-1.5 rounded-lg bg-primary-600/20 text-primary-400 hover:bg-primary-600/30 transition-colors"
          title="Add Step"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-2">
        {steps.map((step, index) => (
          <div
            key={step.id || `new-${index}`}
            onClick={() => onSelect(index)}
            className={`group relative p-3 rounded-lg border cursor-pointer transition-all ${
              selectedIndex === index
                ? 'bg-primary-900/30 border-primary-600'
                : 'bg-gray-800 border-gray-700 hover:border-gray-600'
            }`}
          >
            {/* Step Number Badge */}
            <div className="absolute -left-2 -top-2 w-6 h-6 rounded-full bg-gray-700 border-2 border-gray-900 flex items-center justify-center">
              <span className="text-xs font-medium text-gray-300">{index + 1}</span>
            </div>

            {/* Step Content */}
            <div className="ml-2">
              <div className="flex items-center gap-2 mb-1">
                {getStatusIndicator(step.status)}
                <span className="font-medium text-white truncate flex-1">
                  {step.name || 'Untitled Step'}
                </span>
              </div>

              <div className="flex items-center gap-2">
                <span className={`text-xs px-1.5 py-0.5 rounded border ${getStepTypeColor(step.step_type)}`}>
                  {getStepTypeLabel(step.step_type)}
                </span>
                {step.config?.model && step.step_type === 'autonomous' && (
                  <span className="text-xs text-gray-500">{step.config.model}</span>
                )}
              </div>
            </div>

            {/* Reorder Arrows */}
            {steps.length > 1 && (
              <div className={`absolute right-2 top-1/2 -translate-y-1/2 flex flex-col ${
                selectedIndex === index ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'
              } transition-opacity`}>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onMove(index, 'up')
                  }}
                  disabled={index === 0}
                  className="p-0.5 text-gray-500 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed"
                  title="Move up"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                  </svg>
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    onMove(index, 'down')
                  }}
                  disabled={index === steps.length - 1}
                  className="p-0.5 text-gray-500 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed"
                  title="Move down"
                >
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
              </div>
            )}
          </div>
        ))}

        {steps.length === 0 && (
          <div className="text-center py-8 text-gray-500 text-sm">
            No steps yet
          </div>
        )}
      </div>

      {/* Add Step Button at Bottom */}
      <button
        onClick={onAdd}
        className="mt-3 w-full py-2 px-3 rounded-lg border-2 border-dashed border-gray-700 text-gray-400 hover:border-primary-600 hover:text-primary-400 transition-colors flex items-center justify-center gap-2"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
        </svg>
        <span className="text-sm">Add Step</span>
      </button>
    </div>
  )
}
