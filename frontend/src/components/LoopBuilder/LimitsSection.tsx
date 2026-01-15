import { LoopLimits } from './types'
import { HelpIcon } from '../Help'
import { LOOP_BUILDER_HELP } from '../../content/help'

interface LimitsSectionProps {
  limits: LoopLimits
  onChange: (limits: LoopLimits) => void
}

export default function LimitsSection({ limits, onChange }: LimitsSectionProps) {
  const handleChange = (key: keyof LoopLimits, value: number) => {
    onChange({ ...limits, [key]: value })
  }

  // Format seconds to human-readable duration
  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`
  }

  return (
    <section>
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
        <span className="w-8 h-8 rounded-full bg-primary-600 text-white flex items-center justify-center text-sm font-bold mr-3">
          5
        </span>
        Execution Limits
      </h3>

      <div className="space-y-4 pl-11">
        <p className="text-sm text-gray-400">
          Set safety limits to prevent runaway loops and manage resource usage.
        </p>

        <div className="grid grid-cols-2 gap-4">
          {/* Max Iterations */}
          <div className="p-4 bg-gray-700/50 rounded-lg border border-gray-600">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Max Iterations
              <HelpIcon content={LOOP_BUILDER_HELP.maxIterations.body} size="sm" className="ml-1" />
            </label>
            <input
              type="number"
              value={limits.max_iterations}
              onChange={(e) => handleChange('max_iterations', parseInt(e.target.value) || 0)}
              min={0}
              max={10000}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-primary-500"
            />
            <p className="mt-2 text-xs text-gray-500">
              {limits.max_iterations === 0
                ? 'Unlimited iterations'
                : `Loop will stop after ${limits.max_iterations} iterations`}
            </p>
          </div>

          {/* Max Runtime */}
          <div className="p-4 bg-gray-700/50 rounded-lg border border-gray-600">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Max Runtime
              <HelpIcon content={LOOP_BUILDER_HELP.maxRuntime.body} size="sm" className="ml-1" />
            </label>
            <div className="flex items-center space-x-2">
              <input
                type="number"
                value={limits.max_runtime_seconds}
                onChange={(e) => handleChange('max_runtime_seconds', parseInt(e.target.value) || 0)}
                min={0}
                max={86400}
                className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-primary-500"
              />
              <span className="text-sm text-gray-400">seconds</span>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              {limits.max_runtime_seconds === 0
                ? 'Unlimited runtime'
                : `Loop will stop after ${formatDuration(limits.max_runtime_seconds)}`}
            </p>
          </div>

          {/* Max Consecutive Errors */}
          <div className="p-4 bg-gray-700/50 rounded-lg border border-gray-600">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Max Consecutive Errors
              <HelpIcon content={LOOP_BUILDER_HELP.maxErrors.body} size="sm" className="ml-1" />
            </label>
            <input
              type="number"
              value={limits.max_consecutive_errors}
              onChange={(e) => handleChange('max_consecutive_errors', parseInt(e.target.value) || 1)}
              min={1}
              max={100}
              className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-primary-500"
            />
            <p className="mt-2 text-xs text-gray-500">
              Loop stops if {limits.max_consecutive_errors} errors occur in a row
            </p>
          </div>

          {/* Cooldown Between Iterations */}
          <div className="p-4 bg-gray-700/50 rounded-lg border border-gray-600">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Cooldown Between Iterations
              <HelpIcon content={LOOP_BUILDER_HELP.cooldown.body} size="sm" className="ml-1" />
            </label>
            <div className="flex items-center space-x-2">
              <input
                type="number"
                value={limits.cooldown_between_iterations}
                onChange={(e) => handleChange('cooldown_between_iterations', parseInt(e.target.value) || 0)}
                min={0}
                max={3600}
                className="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-primary-500"
              />
              <span className="text-sm text-gray-400">seconds</span>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Wait time between each iteration
            </p>
          </div>
        </div>

        {/* Quick presets */}
        <div className="flex flex-wrap gap-2 pt-2">
          <span className="text-sm text-gray-400 mr-2">Quick presets:</span>
          <button
            type="button"
            onClick={() =>
              onChange({
                max_iterations: 10,
                max_runtime_seconds: 3600,
                max_consecutive_errors: 3,
                cooldown_between_iterations: 5,
              })
            }
            className="px-3 py-1 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
          >
            Quick test (10 iter)
          </button>
          <button
            type="button"
            onClick={() =>
              onChange({
                max_iterations: 100,
                max_runtime_seconds: 28800,
                max_consecutive_errors: 5,
                cooldown_between_iterations: 5,
              })
            }
            className="px-3 py-1 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
          >
            Standard (100 iter, 8h)
          </button>
          <button
            type="button"
            onClick={() =>
              onChange({
                max_iterations: 0,
                max_runtime_seconds: 86400,
                max_consecutive_errors: 10,
                cooldown_between_iterations: 10,
              })
            }
            className="px-3 py-1 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
          >
            Long run (unlimited, 24h)
          </button>
        </div>
      </div>
    </section>
  )
}
