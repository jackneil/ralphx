import { ModeConfig, ModeSelection } from './types'

interface StrategySectionProps {
  strategy: ModeSelection
  modes: ModeConfig[]
  onChange: (strategy: ModeSelection) => void
}

export default function StrategySection({
  strategy,
  modes,
  onChange,
}: StrategySectionProps) {
  const handleStrategyChange = (newStrategy: ModeSelection['strategy']) => {
    const updated: ModeSelection = { strategy: newStrategy }

    if (newStrategy === 'fixed' && modes.length > 0) {
      updated.fixed_mode = modes[0].name
    }

    if (newStrategy === 'weighted_random') {
      const weights: Record<string, number> = {}
      const equalWeight = Math.floor(100 / modes.length)
      modes.forEach((mode) => {
        weights[mode.name] = equalWeight
      })
      updated.weights = weights
    }

    onChange(updated)
  }

  const handleFixedModeChange = (modeName: string) => {
    onChange({ ...strategy, fixed_mode: modeName })
  }

  const handleWeightChange = (modeName: string, weight: number) => {
    onChange({
      ...strategy,
      weights: {
        ...strategy.weights,
        [modeName]: weight,
      },
    })
  }

  // Calculate total weight for percentage display
  const totalWeight = strategy.weights
    ? Object.values(strategy.weights).reduce((sum, w) => sum + w, 0)
    : 0

  return (
    <section>
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
        <span className="w-8 h-8 rounded-full bg-primary-600 text-white flex items-center justify-center text-sm font-bold mr-3">
          4
        </span>
        Mode Selection Strategy
      </h3>

      <div className="space-y-4 pl-11">
        <p className="text-sm text-gray-400">
          Choose how the loop selects which mode to use for each iteration.
        </p>

        {/* Strategy Radio Options */}
        <div className="space-y-3">
          {/* Fixed */}
          <label className="flex items-start space-x-3 p-3 bg-gray-700/50 rounded-lg border border-gray-600 cursor-pointer hover:bg-gray-700/70 transition-colors">
            <input
              type="radio"
              name="strategy"
              checked={strategy.strategy === 'fixed'}
              onChange={() => handleStrategyChange('fixed')}
              className="mt-1"
            />
            <div className="flex-1">
              <div className="font-medium text-white">Fixed</div>
              <div className="text-xs text-gray-400 mt-1">
                Always use the same mode for every iteration
              </div>
              {strategy.strategy === 'fixed' && modes.length > 0 && (
                <select
                  value={strategy.fixed_mode || modes[0]?.name || ''}
                  onChange={(e) => handleFixedModeChange(e.target.value)}
                  className="mt-2 w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white focus:outline-none focus:border-primary-500"
                >
                  {modes.map((mode) => (
                    <option key={mode.name} value={mode.name}>
                      {mode.name}
                    </option>
                  ))}
                </select>
              )}
            </div>
          </label>

          {/* Random */}
          <label className="flex items-start space-x-3 p-3 bg-gray-700/50 rounded-lg border border-gray-600 cursor-pointer hover:bg-gray-700/70 transition-colors">
            <input
              type="radio"
              name="strategy"
              checked={strategy.strategy === 'random'}
              onChange={() => handleStrategyChange('random')}
              className="mt-1"
            />
            <div className="flex-1">
              <div className="font-medium text-white">Random</div>
              <div className="text-xs text-gray-400 mt-1">
                Randomly select a mode with equal probability
              </div>
            </div>
          </label>

          {/* Weighted Random */}
          <label className="flex items-start space-x-3 p-3 bg-gray-700/50 rounded-lg border border-gray-600 cursor-pointer hover:bg-gray-700/70 transition-colors">
            <input
              type="radio"
              name="strategy"
              checked={strategy.strategy === 'weighted_random'}
              onChange={() => handleStrategyChange('weighted_random')}
              className="mt-1"
            />
            <div className="flex-1">
              <div className="font-medium text-white">Weighted Random</div>
              <div className="text-xs text-gray-400 mt-1">
                Randomly select a mode based on specified weights
              </div>
              {strategy.strategy === 'weighted_random' && modes.length > 0 && (
                <div className="mt-3 space-y-2">
                  {modes.map((mode) => {
                    const weight = strategy.weights?.[mode.name] || 0
                    const percentage = totalWeight > 0 ? ((weight / totalWeight) * 100).toFixed(0) : 0
                    return (
                      <div key={mode.name} className="flex items-center space-x-3">
                        <span className="text-sm text-gray-300 w-24 truncate" title={mode.name}>
                          {mode.name}
                        </span>
                        <input
                          type="range"
                          min={0}
                          max={100}
                          value={weight}
                          onChange={(e) => handleWeightChange(mode.name, parseInt(e.target.value))}
                          className="flex-1 h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer accent-primary-500"
                        />
                        <span className="text-sm text-gray-400 w-16 text-right">
                          {percentage}%
                        </span>
                      </div>
                    )
                  })}
                  {totalWeight !== 100 && (
                    <p className="text-xs text-yellow-400 mt-2">
                      Weights will be normalized to 100%
                    </p>
                  )}
                </div>
              )}
            </div>
          </label>
        </div>

        {modes.length === 0 && (
          <p className="text-sm text-yellow-400">
            Add at least one mode to configure the selection strategy
          </p>
        )}
      </div>
    </section>
  )
}
