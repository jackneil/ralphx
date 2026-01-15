import { ItemTypes, ItemTypeConfig } from './types'
import { HelpIcon } from '../Help'
import { LOOP_BUILDER_HELP } from '../../content/help'

interface ItemTypesSectionProps {
  itemTypes: ItemTypes
  loopType: 'generator' | 'consumer' | 'hybrid'
  availableLoops: string[]
  onChange: (itemTypes: ItemTypes) => void
}

interface ItemTypeFieldsProps {
  label: string
  config: ItemTypeConfig
  showSource?: boolean
  availableLoops?: string[]
  onChange: (config: ItemTypeConfig) => void
}

function ItemTypeFields({
  label,
  config,
  showSource = false,
  availableLoops = [],
  onChange,
}: ItemTypeFieldsProps) {
  return (
    <div className="p-4 bg-gray-700/50 rounded-lg border border-gray-600">
      <h5 className="text-sm font-medium text-white mb-3">{label}</h5>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Singular
          </label>
          <input
            type="text"
            value={config.singular}
            onChange={(e) => onChange({ ...config, singular: e.target.value })}
            placeholder="e.g., story"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">
            Plural
          </label>
          <input
            type="text"
            value={config.plural}
            onChange={(e) => onChange({ ...config, plural: e.target.value })}
            placeholder="e.g., stories"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
          />
        </div>
      </div>
      <div className="mt-3">
        <label className="block text-xs text-gray-400 mb-1">
          Description
        </label>
        <input
          type="text"
          value={config.description}
          onChange={(e) => onChange({ ...config, description: e.target.value })}
          placeholder="e.g., User stories with acceptance criteria"
          className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
        />
      </div>
      {showSource && (
        <div className="mt-3">
          <label className="block text-xs text-gray-400 mb-1">
            Source Loop
            <HelpIcon content={LOOP_BUILDER_HELP.sourceLoop.body} size="sm" className="ml-1" />
          </label>
          <select
            value={config.source || ''}
            onChange={(e) => onChange({ ...config, source: e.target.value || undefined })}
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-sm text-white focus:outline-none focus:border-primary-500"
          >
            <option value="">Select a source loop...</option>
            {availableLoops.map((loop) => (
              <option key={loop} value={loop}>
                {loop}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-gray-500">
            Which loop's output items should this loop consume?
          </p>
        </div>
      )}
    </div>
  )
}

export default function ItemTypesSection({
  itemTypes,
  loopType,
  availableLoops,
  onChange,
}: ItemTypesSectionProps) {
  const showInput = loopType === 'consumer' || loopType === 'hybrid'

  const handleOutputChange = (output: ItemTypeConfig) => {
    onChange({ ...itemTypes, output })
  }

  const handleInputChange = (input: ItemTypeConfig) => {
    onChange({ ...itemTypes, input })
  }

  const handleAddInput = () => {
    onChange({
      ...itemTypes,
      input: {
        singular: 'item',
        plural: 'items',
        description: '',
      },
    })
  }

  const handleRemoveInput = () => {
    const { input: _, ...rest } = itemTypes
    onChange({ ...rest, output: itemTypes.output })
  }

  return (
    <section>
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
        <span className="w-8 h-8 rounded-full bg-primary-600 text-white flex items-center justify-center text-sm font-bold mr-3">
          2
        </span>
        Item Types
        <HelpIcon content={LOOP_BUILDER_HELP.itemTypes.body} size="sm" className="ml-2" />
      </h3>

      <div className="space-y-4 pl-11">
        <p className="text-sm text-gray-400">
          Configure how items are named in the UI. This helps make the interface more intuitive
          for your specific use case.
        </p>

        {/* Input Type (for consumer/hybrid) */}
        {showInput && (
          <div>
            {itemTypes.input ? (
              <div className="relative">
                <ItemTypeFields
                  label="Input Item Type"
                  config={itemTypes.input}
                  showSource={true}
                  availableLoops={availableLoops}
                  onChange={handleInputChange}
                />
                <button
                  type="button"
                  onClick={handleRemoveInput}
                  className="absolute top-2 right-2 text-gray-400 hover:text-red-400"
                  title="Remove input type"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ) : (
              <button
                type="button"
                onClick={handleAddInput}
                className="w-full p-4 border-2 border-dashed border-gray-600 rounded-lg text-gray-400 hover:border-gray-500 hover:text-gray-300 transition-colors"
              >
                <div className="flex items-center justify-center space-x-2">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  <span>Add Input Item Type</span>
                </div>
                <p className="text-xs mt-1">
                  Define the items this loop will consume from another loop
                </p>
              </button>
            )}
          </div>
        )}

        {/* Arrow for consumer/hybrid */}
        {showInput && itemTypes.input && (
          <div className="flex justify-center py-2">
            <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
          </div>
        )}

        {/* Output Type (always shown) */}
        <ItemTypeFields
          label="Output Item Type"
          config={itemTypes.output}
          onChange={handleOutputChange}
        />

        {/* Help text */}
        <div className="p-3 bg-gray-700/30 rounded-lg border border-gray-600/50">
          <div className="flex items-start space-x-2">
            <svg className="w-5 h-5 text-primary-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="text-xs text-gray-400">
              <strong className="text-gray-300">Example usage:</strong> For a research loop that generates user stories,
              set Output to singular: "story", plural: "stories". The UI will show "Add Story" instead of "Add Item".
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
