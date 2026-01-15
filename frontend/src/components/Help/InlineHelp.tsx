import { useState, ReactNode, useId } from 'react'

interface InlineHelpProps {
  title?: string
  children: ReactNode
  defaultExpanded?: boolean
  variant?: 'info' | 'tip' | 'warning'
}

const variantStyles = {
  info: {
    container: 'bg-blue-900/20 border-blue-800/50',
    icon: 'text-blue-400',
    title: 'text-blue-300',
    iconPath: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
  },
  tip: {
    container: 'bg-green-900/20 border-green-800/50',
    icon: 'text-green-400',
    title: 'text-green-300',
    iconPath: 'M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z',
  },
  warning: {
    container: 'bg-yellow-900/20 border-yellow-800/50',
    icon: 'text-yellow-400',
    title: 'text-yellow-300',
    iconPath: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z',
  },
}

export default function InlineHelp({
  title,
  children,
  defaultExpanded = false,
  variant = 'info',
}: InlineHelpProps) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const styles = variantStyles[variant]
  const contentId = useId()

  return (
    <div className={`rounded-lg border ${styles.container}`}>
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full px-4 py-3 flex items-center justify-between text-left"
        aria-expanded={expanded}
        aria-controls={contentId}
      >
        <div className="flex items-center space-x-3">
          <svg className={`w-5 h-5 ${styles.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={styles.iconPath} />
          </svg>
          <span className={`text-sm font-medium ${styles.title}`}>
            {title || (variant === 'tip' ? 'Tip' : variant === 'warning' ? 'Warning' : 'Help')}
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div id={contentId} className="px-4 pb-4 pt-0">
          <div className="text-sm text-gray-300 pl-8">{children}</div>
        </div>
      )}
    </div>
  )
}
