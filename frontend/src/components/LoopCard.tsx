import { Link } from 'react-router-dom'
import type { Loop } from '../stores/dashboard'
import ProgressBar from './ProgressBar'

interface LoopCardProps {
  projectSlug: string
  loop: Loop
  maxIterations?: number
}

// Extract a friendly date from loop name like "implementation_20260116_1" -> "Jan 16"
function extractDateFromName(name: string): string | null {
  const match = name.match(/_(\d{4})(\d{2})(\d{2})_/)
  if (match) {
    const [, year, month, day] = match
    const date = new Date(parseInt(year), parseInt(month) - 1, parseInt(day))
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  }
  return null
}

// Extract instance number from loop name like "implementation_20260116_1" -> "#1"
function extractInstanceFromName(name: string): string | null {
  const match = name.match(/_(\d+)$/)
  return match ? `#${match[1]}` : null
}

// Get mode names from modes array (which contains objects with 'name' property)
function getModeNames(modes: unknown): string {
  if (Array.isArray(modes)) {
    return modes
      .map(m => typeof m === 'string' ? m : (m?.name || 'unknown'))
      .join(', ')
  }
  if (typeof modes === 'object' && modes !== null) {
    return Object.keys(modes).join(', ')
  }
  return 'default'
}

export default function LoopCard({ projectSlug, loop, maxIterations = 100 }: LoopCardProps) {
  const progress = loop.current_iteration
    ? (loop.current_iteration / maxIterations) * 100
    : 0

  const dateStr = extractDateFromName(loop.name)
  const instance = extractInstanceFromName(loop.name)
  const modeNames = getModeNames(loop.modes)

  return (
    <Link
      to={`/projects/${projectSlug}/loops/${loop.name}`}
      className="card hover:bg-gray-700 transition-colors block"
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-semibold text-white">
            {loop.display_name}
          </h3>
          {instance && (
            <span className="text-xs bg-gray-700 text-gray-300 px-1.5 py-0.5 rounded">
              {instance}
            </span>
          )}
        </div>
        <StatusIndicator isRunning={loop.is_running} />
      </div>

      {/* Loop ID for clarity */}
      <div className="text-xs text-gray-500 font-mono mb-2 truncate" title={loop.name}>
        {loop.name}
      </div>

      <div className="flex items-center gap-4 text-sm text-gray-400 mb-2">
        <span>
          Type: <span className="text-gray-300">{loop.type}</span>
        </span>
        {dateStr && (
          <span className="text-gray-500">
            {dateStr}
          </span>
        )}
      </div>

      <div className="text-xs text-gray-500 mb-3">
        Modes: {modeNames}
      </div>

      {loop.is_running && (
        <div className="space-y-2">
          <ProgressBar
            value={progress}
            label={`Iteration ${loop.current_iteration || 0}`}
          />
          {loop.current_mode && (
            <div className="text-sm text-primary-400">
              Mode: {loop.current_mode}
            </div>
          )}
        </div>
      )}
    </Link>
  )
}

function StatusIndicator({ isRunning }: { isRunning: boolean }) {
  return (
    <div className="flex items-center space-x-2">
      <span
        className={`w-2.5 h-2.5 rounded-full ${
          isRunning ? 'bg-green-400 animate-pulse' : 'bg-gray-500'
        }`}
      />
      <span className={`text-sm ${isRunning ? 'text-green-400' : 'text-gray-400'}`}>
        {isRunning ? 'Running' : 'Stopped'}
      </span>
    </div>
  )
}
