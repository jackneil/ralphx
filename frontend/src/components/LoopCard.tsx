import { Link } from 'react-router-dom'
import type { Loop } from '../stores/dashboard'
import ProgressBar from './ProgressBar'

interface LoopCardProps {
  projectSlug: string
  loop: Loop
  maxIterations?: number
}

export default function LoopCard({ projectSlug, loop, maxIterations = 100 }: LoopCardProps) {
  const progress = loop.current_iteration
    ? (loop.current_iteration / maxIterations) * 100
    : 0

  return (
    <Link
      to={`/projects/${projectSlug}/loops/${loop.name}`}
      className="card hover:bg-gray-700 transition-colors block"
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-white">
          {loop.display_name}
        </h3>
        <StatusIndicator isRunning={loop.is_running} />
      </div>

      <div className="text-sm text-gray-400 mb-3">
        Type: <span className="text-gray-300">{loop.type}</span>
      </div>

      <div className="text-xs text-gray-500 mb-3">
        Modes: {loop.modes.join(', ')}
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
