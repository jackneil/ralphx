import type { WorkflowStep } from '../../api'

interface WorkflowTimelineProps {
  steps: WorkflowStep[]
  currentStep: number
}

export default function WorkflowTimeline({ steps, currentStep }: WorkflowTimelineProps) {
  // Note: currentStep is used to determine highlight state, but we derive it from step.status
  // Keeping the prop for consistency with parent component contract
  void currentStep // Acknowledge prop to prevent unused warning
  const getStepStatusColor = (step: WorkflowStep) => {
    switch (step.status) {
      case 'completed':
        return 'bg-green-500'
      case 'active':
        return 'bg-primary-500 animate-pulse'
      case 'skipped':
        return 'bg-gray-500'
      default:
        return 'bg-gray-600'
    }
  }

  const getStepIcon = (step: WorkflowStep) => {
    if (step.status === 'completed') {
      return (
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      )
    }
    if (step.status === 'skipped') {
      return (
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
        </svg>
      )
    }
    if (step.status === 'active') {
      return (
        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      )
    }
    return <span className="text-sm font-bold text-white">{step.step_number}</span>
  }

  const getConnectorColor = (index: number) => {
    const step = steps[index]
    if (step.status === 'completed' || step.status === 'skipped') {
      return 'bg-green-500'
    }
    return 'bg-gray-600'
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between">
        {steps.map((step, index) => (
          <div key={step.id} className="flex items-center flex-1">
            {/* Step Node */}
            <div className="flex flex-col items-center">
              <div
                className={`w-10 h-10 rounded-full flex items-center justify-center ${getStepStatusColor(step)}`}
              >
                {getStepIcon(step)}
              </div>
              <div className="mt-2 text-center">
                <div className={`text-sm font-medium ${step.status === 'active' ? 'text-white' : 'text-gray-400'}`}>
                  {step.name}
                </div>
                <div className="text-xs text-gray-500">
                  {step.step_type === 'interactive' ? 'Chat' : 'Auto'}
                </div>
              </div>
            </div>

            {/* Connector */}
            {index < steps.length - 1 && (
              <div className={`flex-1 h-1 mx-2 ${getConnectorColor(index)}`} />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
