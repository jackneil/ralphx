import { ReactNode } from 'react'

interface Step {
  title: string
  description: ReactNode
}

interface StepGuideProps {
  steps: Step[]
}

export default function StepGuide({ steps }: StepGuideProps) {
  return (
    <div className="space-y-4">
      {steps.map((step, index) => (
        <div key={index} className="flex space-x-4">
          {/* Step number */}
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-cyan-500/20 border border-cyan-500/30 flex items-center justify-center">
            <span className="text-sm font-semibold text-cyan-400">{index + 1}</span>
          </div>

          {/* Step content */}
          <div className="flex-1 pt-1">
            <h4 className="text-sm font-medium text-white mb-1">{step.title}</h4>
            <div className="text-sm text-gray-400">{step.description}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
