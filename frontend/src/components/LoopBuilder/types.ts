/**
 * Types for the Loop Builder component
 */

export interface ItemTypeConfig {
  singular: string
  plural: string
  description: string
  source?: string
}

export interface ItemTypes {
  input?: ItemTypeConfig
  output: ItemTypeConfig
}

export interface ModeConfig {
  name: string
  description: string
  model: string
  timeout: number
  tools: string[]
  prompt_template: string
}

export interface ModeSelection {
  strategy: 'fixed' | 'random' | 'weighted_random'
  fixed_mode?: string
  weights?: Record<string, number>
}

export interface LoopLimits {
  max_iterations: number
  max_runtime_seconds: number
  max_consecutive_errors: number
  cooldown_between_iterations: number
}

export interface LoopFormState {
  name: string
  display_name: string
  type: 'generator' | 'consumer' | 'hybrid'
  description: string
  item_types: ItemTypes
  modes: ModeConfig[]
  mode_selection: ModeSelection
  limits: LoopLimits
}

export const defaultItemTypes: ItemTypes = {
  output: {
    singular: 'item',
    plural: 'items',
    description: '',
  },
}

export const defaultModeSelection: ModeSelection = {
  strategy: 'fixed',
}

export const defaultLimits: LoopLimits = {
  max_iterations: 10,
  max_runtime_seconds: 3600,
  max_consecutive_errors: 3,
  cooldown_between_iterations: 5,
}

export const defaultFormState: LoopFormState = {
  name: '',
  display_name: '',
  type: 'generator',
  description: '',
  item_types: defaultItemTypes,
  modes: [],
  mode_selection: defaultModeSelection,
  limits: defaultLimits,
}

// Convert YAML object to form state
export function yamlToFormState(yaml: Record<string, unknown>): LoopFormState {
  const state = { ...defaultFormState }

  if (typeof yaml.name === 'string') state.name = yaml.name
  if (typeof yaml.display_name === 'string') state.display_name = yaml.display_name
  if (typeof yaml.description === 'string') state.description = yaml.description
  if (yaml.type === 'generator' || yaml.type === 'consumer' || yaml.type === 'hybrid') {
    state.type = yaml.type
  }

  // Parse item_types
  if (yaml.item_types && typeof yaml.item_types === 'object') {
    const it = yaml.item_types as Record<string, unknown>
    state.item_types = {
      output: {
        singular: (it.output as Record<string, unknown>)?.singular as string || 'item',
        plural: (it.output as Record<string, unknown>)?.plural as string || 'items',
        description: (it.output as Record<string, unknown>)?.description as string || '',
        source: (it.output as Record<string, unknown>)?.source as string | undefined,
      },
    }
    if (it.input && typeof it.input === 'object') {
      const input = it.input as Record<string, unknown>
      state.item_types.input = {
        singular: input.singular as string || 'item',
        plural: input.plural as string || 'items',
        description: input.description as string || '',
        source: input.source as string | undefined,
      }
    }
  }

  // Parse modes
  if (yaml.modes && typeof yaml.modes === 'object') {
    const modesObj = yaml.modes as Record<string, unknown>
    state.modes = Object.entries(modesObj).map(([name, mode]) => {
      const m = mode as Record<string, unknown>
      return {
        name,
        description: m.description as string || '',
        model: m.model as string || 'claude-sonnet-4-20250514',
        timeout: typeof m.timeout === 'number' ? m.timeout : 300,
        tools: Array.isArray(m.tools) ? m.tools as string[] : [],
        prompt_template: m.prompt_template as string || '',
      }
    })
  }

  // Parse mode_selection
  if (yaml.mode_selection && typeof yaml.mode_selection === 'object') {
    const ms = yaml.mode_selection as Record<string, unknown>
    state.mode_selection = {
      strategy: ms.strategy as 'fixed' | 'random' | 'weighted_random' || 'fixed',
      fixed_mode: ms.fixed_mode as string | undefined,
      weights: ms.weights as Record<string, number> | undefined,
    }
  }

  // Parse limits
  if (yaml.limits && typeof yaml.limits === 'object') {
    const l = yaml.limits as Record<string, unknown>
    state.limits = {
      max_iterations: typeof l.max_iterations === 'number' ? l.max_iterations : 10,
      max_runtime_seconds: typeof l.max_runtime_seconds === 'number' ? l.max_runtime_seconds : 3600,
      max_consecutive_errors: typeof l.max_consecutive_errors === 'number' ? l.max_consecutive_errors : 3,
      cooldown_between_iterations: typeof l.cooldown_between_iterations === 'number' ? l.cooldown_between_iterations : 5,
    }
  }

  return state
}

// Convert form state to YAML object
export function formStateToYaml(state: LoopFormState): Record<string, unknown> {
  const yaml: Record<string, unknown> = {
    name: state.name,
    display_name: state.display_name,
    type: state.type,
  }

  if (state.description) {
    yaml.description = state.description
  }

  // Build item_types
  const itemTypes: Record<string, unknown> = {
    output: {
      singular: state.item_types.output.singular,
      plural: state.item_types.output.plural,
    },
  }
  if (state.item_types.output.description) {
    (itemTypes.output as Record<string, unknown>).description = state.item_types.output.description
  }
  if (state.item_types.input) {
    itemTypes.input = {
      singular: state.item_types.input.singular,
      plural: state.item_types.input.plural,
    }
    if (state.item_types.input.description) {
      (itemTypes.input as Record<string, unknown>).description = state.item_types.input.description
    }
    if (state.item_types.input.source) {
      (itemTypes.input as Record<string, unknown>).source = state.item_types.input.source
    }
  }
  yaml.item_types = itemTypes

  // Build modes
  const modes: Record<string, unknown> = {}
  for (const mode of state.modes) {
    modes[mode.name] = {
      description: mode.description,
      model: mode.model,
      timeout: mode.timeout,
      prompt_template: mode.prompt_template,
    }
    if (mode.tools.length > 0) {
      (modes[mode.name] as Record<string, unknown>).tools = mode.tools
    }
  }
  yaml.modes = modes

  // Build mode_selection
  const modeSelection: Record<string, unknown> = {
    strategy: state.mode_selection.strategy,
  }
  if (state.mode_selection.strategy === 'fixed' && state.mode_selection.fixed_mode) {
    modeSelection.fixed_mode = state.mode_selection.fixed_mode
  }
  if (state.mode_selection.strategy === 'weighted_random' && state.mode_selection.weights) {
    modeSelection.weights = state.mode_selection.weights
  }
  yaml.mode_selection = modeSelection

  // Build limits
  yaml.limits = {
    max_iterations: state.limits.max_iterations,
    max_runtime_seconds: state.limits.max_runtime_seconds,
    max_consecutive_errors: state.limits.max_consecutive_errors,
    cooldown_between_iterations: state.limits.cooldown_between_iterations,
  }

  return yaml
}
