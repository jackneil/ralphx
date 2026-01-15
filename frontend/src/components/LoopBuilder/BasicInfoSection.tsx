import { HelpIcon } from '../Help'
import { LOOP_BUILDER_HELP } from '../../content/help'

interface BasicInfoSectionProps {
  name: string
  displayName: string
  type: 'generator' | 'consumer' | 'hybrid'
  description: string
  isNewLoop: boolean
  onChange: (updates: {
    name?: string
    display_name?: string
    type?: 'generator' | 'consumer' | 'hybrid'
    description?: string
  }) => void
}

export default function BasicInfoSection({
  name,
  displayName,
  type,
  description,
  isNewLoop,
  onChange,
}: BasicInfoSectionProps) {
  // Auto-generate slug from display name for new loops
  const handleDisplayNameChange = (value: string) => {
    const updates: Parameters<typeof onChange>[0] = { display_name: value }
    if (isNewLoop && !name) {
      // Auto-generate slug
      const slug = value
        .toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .substring(0, 50)
      updates.name = slug
    }
    onChange(updates)
  }

  return (
    <section>
      <h3 className="text-lg font-semibold text-white mb-4 flex items-center">
        <span className="w-8 h-8 rounded-full bg-primary-600 text-white flex items-center justify-center text-sm font-bold mr-3">
          1
        </span>
        Basic Information
      </h3>

      <div className="space-y-4 pl-11">
        {/* Display Name */}
        <div>
          <label htmlFor="display_name" className="block text-sm font-medium text-gray-300 mb-1">
            Display Name <span className="text-red-400">*</span>
            <HelpIcon content={LOOP_BUILDER_HELP.displayName.body} size="sm" className="ml-1" />
          </label>
          <input
            id="display_name"
            type="text"
            value={displayName}
            onChange={(e) => handleDisplayNameChange(e.target.value)}
            placeholder="e.g., Research Loop"
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
          />
          <p className="mt-1 text-xs text-gray-500">
            Human-readable name shown in the UI
          </p>
        </div>

        {/* Slug/Name */}
        <div>
          <label htmlFor="name" className="block text-sm font-medium text-gray-300 mb-1">
            Slug <span className="text-red-400">*</span>
            <HelpIcon content={LOOP_BUILDER_HELP.loopName.body} size="sm" className="ml-1" />
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="e.g., research"
            disabled={!isNewLoop}
            className={`w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500 font-mono ${
              !isNewLoop ? 'opacity-60 cursor-not-allowed' : ''
            }`}
          />
          <p className="mt-1 text-xs text-gray-500">
            {isNewLoop
              ? 'Unique identifier (lowercase letters, numbers, hyphens, underscores)'
              : 'Slug cannot be changed after creation'}
          </p>
        </div>

        {/* Type */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Loop Type <span className="text-red-400">*</span>
            <HelpIcon content={LOOP_BUILDER_HELP.loopType.body} size="sm" className="ml-1" />
          </label>
          <div className="grid grid-cols-3 gap-3">
            {[
              {
                value: 'generator',
                label: 'Generator',
                description: 'Creates new items from prompts',
              },
              {
                value: 'consumer',
                label: 'Consumer',
                description: 'Processes items from another loop',
              },
              {
                value: 'hybrid',
                label: 'Hybrid',
                description: 'Both consumes and generates items',
              },
            ].map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onChange({ type: option.value as typeof type })}
                className={`p-3 rounded-lg border text-left transition-colors ${
                  type === option.value
                    ? 'border-primary-500 bg-primary-900/30'
                    : 'border-gray-600 bg-gray-700 hover:border-gray-500'
                }`}
              >
                <div className="font-medium text-white">{option.label}</div>
                <div className="text-xs text-gray-400 mt-1">{option.description}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Description */}
        <div>
          <label htmlFor="description" className="block text-sm font-medium text-gray-300 mb-1">
            Description
          </label>
          <textarea
            id="description"
            value={description}
            onChange={(e) => onChange({ description: e.target.value })}
            placeholder="Brief description of what this loop does..."
            rows={2}
            className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500 resize-none"
          />
        </div>
      </div>
    </section>
  )
}
