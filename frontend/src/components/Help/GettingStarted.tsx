import { useState, useEffect } from 'react'

interface GettingStartedProps {
  onDismiss?: () => void
  storageKey?: string
}

interface Step {
  title: string
  description: string
  icon: string
  completed?: boolean
}

const STEPS: Step[] = [
  {
    title: 'Create a Project',
    description: 'Point RalphX at a directory to start managing loops for that codebase.',
    icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
  },
  {
    title: 'Configure a Loop',
    description: 'Create loops that define how your AI agent iterates - modes, limits, and item types.',
    icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
  },
  {
    title: 'Add Items',
    description: 'Create items for your loops to process - stories, tasks, or any work units you define.',
    icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4',
  },
  {
    title: 'Run Your Loop',
    description: 'Start the loop and watch as the AI agent processes items according to your configuration.',
    icon: 'M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z',
  },
]

export default function GettingStarted({ onDismiss, storageKey = 'ralphx-onboarding-dismissed' }: GettingStartedProps) {
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    try {
      const wasDismissed = localStorage.getItem(storageKey) === 'true'
      setDismissed(wasDismissed)
    } catch {
      // localStorage may be unavailable (incognito mode, etc.)
    }
  }, [storageKey])

  const handleDismiss = () => {
    try {
      localStorage.setItem(storageKey, 'true')
    } catch {
      // localStorage may be unavailable (incognito mode, etc.)
    }
    setDismissed(true)
    onDismiss?.()
  }

  if (dismissed) {
    return null
  }

  return (
    <div className="bg-gradient-to-r from-primary-900/30 to-purple-900/30 border border-primary-800/50 rounded-lg p-6 mb-6">
      <div className="flex items-start justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold text-white mb-1">Welcome to RalphX</h2>
          <p className="text-gray-400">
            Get started with AI-powered development loops in a few simple steps.
          </p>
        </div>
        <button
          onClick={handleDismiss}
          className="text-gray-400 hover:text-white p-1"
          aria-label="Dismiss getting started guide"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {STEPS.map((step, index) => (
          <div
            key={step.title}
            className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50"
          >
            <div className="flex items-center space-x-3 mb-2">
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-primary-600/20 text-primary-400 flex items-center justify-center">
                <span className="text-sm font-bold">{index + 1}</span>
              </div>
              <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={step.icon} />
              </svg>
            </div>
            <h3 className="text-sm font-medium text-white mb-1">{step.title}</h3>
            <p className="text-xs text-gray-400">{step.description}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-gray-700/50 flex items-center justify-between">
        <p className="text-xs text-gray-500">
          Need help? Check out the documentation or ask in the community.
        </p>
        <button
          onClick={handleDismiss}
          className="text-xs text-primary-400 hover:text-primary-300"
        >
          Don&apos;t show this again
        </button>
      </div>
    </div>
  )
}
