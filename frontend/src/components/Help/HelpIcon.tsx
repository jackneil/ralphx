import { ReactNode } from 'react'
import Tooltip from './Tooltip'

interface HelpIconProps {
  content: ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

const sizeClasses = {
  sm: 'w-3.5 h-3.5',
  md: 'w-4 h-4',
  lg: 'w-5 h-5',
}

export default function HelpIcon({
  content,
  position = 'top',
  size = 'md',
  className = '',
}: HelpIconProps) {
  return (
    <Tooltip content={content} position={position}>
      <button
        type="button"
        className={`inline-flex items-center justify-center rounded-full text-gray-400 hover:text-gray-300 hover:bg-gray-700/50 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 focus:ring-offset-gray-800 ${className}`}
        aria-label="Help"
      >
        <svg
          className={sizeClasses[size]}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
      </button>
    </Tooltip>
  )
}
