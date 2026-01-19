import { useState, ReactNode } from 'react'

interface QuickAnswerProps {
  question: string
  children: ReactNode
  defaultOpen?: boolean
}

export default function QuickAnswer({ question, children, defaultOpen = false }: QuickAnswerProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="border border-gray-700/50 rounded-lg overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-3 flex items-center justify-between text-left bg-gray-800/30 hover:bg-gray-800/50 transition-colors"
      >
        <span className="text-sm font-medium text-gray-200">{question}</span>
        <svg
          className={`w-5 h-5 text-gray-500 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {isOpen && (
        <div className="px-4 py-3 text-sm text-gray-400 border-t border-gray-700/50 bg-gray-900/30">
          {children}
        </div>
      )}
    </div>
  )
}
