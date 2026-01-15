import { useState, useCallback, useEffect, useMemo } from 'react'
import yaml from 'js-yaml'
import {
  LoopFormState,
  defaultFormState,
  yamlToFormState,
  formStateToYaml,
} from './types'
import BasicInfoSection from './BasicInfoSection'
import ItemTypesSection from './ItemTypesSection'
import ModesSection from './ModesSection'
import StrategySection from './StrategySection'
import LimitsSection from './LimitsSection'
import YamlEditor from './YamlEditor'
import TemplateSelector from './TemplateSelector'
import LoopPreview from './LoopPreview'

interface LoopBuilderProps {
  projectSlug: string
  loopName?: string // If provided, editing existing loop
  initialYaml?: string
  availableLoops?: string[] // For source loop dropdown
  onClose: () => void
  onSave: (yamlContent: string) => Promise<void>
}

type TabType = 'visual' | 'yaml' | 'preview'

export default function LoopBuilder({
  projectSlug,
  loopName,
  initialYaml,
  availableLoops = [],
  onClose,
  onSave,
}: LoopBuilderProps) {
  const [activeTab, setActiveTab] = useState<TabType>('visual')
  const [formState, setFormState] = useState<LoopFormState>(defaultFormState)
  const [yamlContent, setYamlContent] = useState('')
  const [yamlError, setYamlError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  // Track original state to detect changes
  const [originalYaml, setOriginalYaml] = useState('')

  // Template selector for new loops
  const isNewLoop = !loopName
  const [showTemplateSelector, setShowTemplateSelector] = useState(isNewLoop && !initialYaml)

  // Initialize from YAML if provided
  useEffect(() => {
    if (initialYaml) {
      setYamlContent(initialYaml)
      setOriginalYaml(initialYaml)
      try {
        const parsed = yaml.load(initialYaml) as Record<string, unknown>
        setFormState(yamlToFormState(parsed))
        setYamlError(null)
      } catch (e) {
        setYamlError(e instanceof Error ? e.message : 'Invalid YAML')
      }
    }
  }, [initialYaml])

  // Sync form state to YAML (debounced)
  const syncFormToYaml = useCallback(() => {
    try {
      const yamlObj = formStateToYaml(formState)
      const newYaml = yaml.dump(yamlObj, {
        indent: 2,
        lineWidth: -1,
        noRefs: true,
        sortKeys: false,
      })
      setYamlContent(newYaml)
      setYamlError(null)
    } catch (e) {
      // Form state should always be valid, but handle errors gracefully
      console.error('Failed to convert form state to YAML:', e)
    }
  }, [formState])

  // Sync YAML to form state (on tab switch or explicit request)
  const syncYamlToForm = useCallback((): boolean => {
    if (!yamlContent.trim()) {
      setYamlError('YAML content is empty')
      return false
    }

    try {
      const parsed = yaml.load(yamlContent) as Record<string, unknown>
      if (typeof parsed !== 'object' || parsed === null) {
        setYamlError('YAML must be an object')
        return false
      }
      setFormState(yamlToFormState(parsed))
      setYamlError(null)
      return true
    } catch (e) {
      setYamlError(e instanceof Error ? e.message : 'Invalid YAML')
      return false
    }
  }, [yamlContent])

  // Auto-sync form -> YAML when form state changes (in visual tab)
  useEffect(() => {
    if (activeTab === 'visual') {
      const timeout = setTimeout(syncFormToYaml, 100)
      return () => clearTimeout(timeout)
    }
  }, [activeTab, formState, syncFormToYaml])

  // Handle tab switch
  const handleTabChange = (tab: TabType) => {
    if (tab === 'yaml' && activeTab === 'visual') {
      // Switching from Visual to YAML - sync form to YAML immediately
      // This ensures any recent form edits are reflected in YAML
      syncFormToYaml()
    } else if (tab === 'visual' && activeTab === 'yaml') {
      // Switching from YAML to Visual - parse YAML first
      if (!syncYamlToForm()) {
        // YAML has errors, don't allow switch until fixed
        // This prevents silent data loss where useEffect would overwrite invalid YAML
        return
      }
    } else if (tab === 'preview' && activeTab === 'yaml') {
      // Sync YAML before showing preview
      if (!syncYamlToForm()) {
        return
      }
    } else if (tab === 'preview' && activeTab === 'visual') {
      // Sync form to YAML before preview (to ensure saved state is reflected)
      syncFormToYaml()
    }
    setActiveTab(tab)
  }

  // Check if there are unsaved changes
  const hasChanges = useMemo(() => {
    return yamlContent !== originalYaml
  }, [yamlContent, originalYaml])

  // Validate form before save
  const validateForm = useCallback((): string | null => {
    if (!formState.name.trim()) {
      return 'Loop name is required'
    }
    if (!/^[a-z0-9_-]+$/.test(formState.name)) {
      return 'Loop name must contain only lowercase letters, numbers, hyphens, and underscores'
    }
    if (!formState.display_name.trim()) {
      return 'Display name is required'
    }
    if (formState.modes.length === 0) {
      return 'At least one mode is required'
    }
    const modeNames = new Set<string>()
    for (const mode of formState.modes) {
      if (!mode.name.trim()) {
        return 'All modes must have a name'
      }
      if (modeNames.has(mode.name)) {
        return `Duplicate mode name: "${mode.name}". Each mode must have a unique name.`
      }
      modeNames.add(mode.name)
      if (!mode.prompt_template.trim()) {
        return `Mode "${mode.name}" must have a prompt template`
      }
    }
    if (formState.mode_selection.strategy === 'fixed') {
      if (!formState.mode_selection.fixed_mode && formState.modes.length > 0) {
        return 'Fixed strategy requires selecting a mode'
      }
    }
    return null
  }, [formState])

  // Handle save
  const handleSave = async () => {
    let contentToSave: string

    // Generate YAML synchronously to avoid race condition with setState
    if (activeTab === 'visual') {
      try {
        const yamlObj = formStateToYaml(formState)
        contentToSave = yaml.dump(yamlObj, {
          indent: 2,
          lineWidth: -1,
          noRefs: true,
          sortKeys: false,
        })
        // Also update state for display consistency
        setYamlContent(contentToSave)
        setYamlError(null)
      } catch (e) {
        setSaveError('Failed to generate YAML from form')
        return
      }
    } else {
      // Parse YAML first
      if (!syncYamlToForm()) {
        setSaveError('Fix YAML errors before saving')
        return
      }
      contentToSave = yamlContent
    }

    // Validate
    const validationError = validateForm()
    if (validationError) {
      setSaveError(validationError)
      return
    }

    setSaving(true)
    setSaveError(null)
    try {
      await onSave(contentToSave)
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  // Handle close with unsaved changes warning
  const handleClose = () => {
    if (hasChanges && !window.confirm('Discard unsaved changes?')) {
      return
    }
    onClose()
  }

  // Update form state helper
  const updateFormState = useCallback((updates: Partial<LoopFormState>) => {
    setFormState((prev) => ({ ...prev, ...updates }))
  }, [])

  // Handle template selection
  const handleTemplateSelect = useCallback((config: Record<string, unknown>, configYaml: string) => {
    setShowTemplateSelector(false)

    if (configYaml && Object.keys(config).length > 0) {
      // Template selected - populate form
      setYamlContent(configYaml)
      setFormState(yamlToFormState(config))
      setYamlError(null)
    }
    // If empty config (start from scratch), keep defaults
  }, [])

  // Show template selector for new loops
  if (showTemplateSelector) {
    return (
      <TemplateSelector
        onSelect={handleTemplateSelect}
        onClose={onClose}
      />
    )
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg w-full max-w-4xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-gray-700 flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-white">
              {isNewLoop ? 'Create New Loop' : `Edit Loop: ${loopName}`}
            </h3>
            <p className="text-sm text-gray-400">
              Project: {projectSlug}
            </p>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-white"
            aria-label="Close"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700">
          <button
            onClick={() => handleTabChange('visual')}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === 'visual'
                ? 'text-white border-b-2 border-primary-500 bg-gray-700/50'
                : 'text-gray-400 hover:text-white hover:bg-gray-700/30'
            }`}
          >
            Visual Editor
          </button>
          <button
            onClick={() => handleTabChange('yaml')}
            className={`px-6 py-3 text-sm font-medium transition-colors ${
              activeTab === 'yaml'
                ? 'text-white border-b-2 border-primary-500 bg-gray-700/50'
                : 'text-gray-400 hover:text-white hover:bg-gray-700/30'
            }`}
          >
            YAML Source
            {yamlError && (
              <span className="ml-2 w-2 h-2 inline-block rounded-full bg-red-500" title="YAML has errors" />
            )}
          </button>
          {/* Preview tab - only for existing loops */}
          {!isNewLoop && loopName && (
            <button
              onClick={() => handleTabChange('preview')}
              className={`px-6 py-3 text-sm font-medium transition-colors ${
                activeTab === 'preview'
                  ? 'text-white border-b-2 border-primary-500 bg-gray-700/50'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/30'
              }`}
            >
              Preview
            </button>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === 'visual' ? (
            <div className="p-6 space-y-6">
              <BasicInfoSection
                name={formState.name}
                displayName={formState.display_name}
                type={formState.type}
                description={formState.description}
                isNewLoop={isNewLoop}
                onChange={(updates) => updateFormState(updates)}
              />

              <ItemTypesSection
                itemTypes={formState.item_types}
                loopType={formState.type}
                availableLoops={availableLoops.filter((l) => l !== formState.name)}
                onChange={(itemTypes) => updateFormState({ item_types: itemTypes })}
              />

              <ModesSection
                modes={formState.modes}
                onChange={(modes) => updateFormState({ modes })}
              />

              <StrategySection
                strategy={formState.mode_selection}
                modes={formState.modes}
                onChange={(mode_selection) => updateFormState({ mode_selection })}
              />

              <LimitsSection
                limits={formState.limits}
                onChange={(limits) => updateFormState({ limits })}
              />
            </div>
          ) : activeTab === 'yaml' ? (
            <YamlEditor
              content={yamlContent}
              error={yamlError}
              onChange={setYamlContent}
            />
          ) : activeTab === 'preview' && loopName ? (
            <LoopPreview
              projectSlug={projectSlug}
              loopName={loopName}
              loopType={formState.type}
            />
          ) : null}
        </div>

        {/* Error */}
        {saveError && (
          <div className="px-4 pb-2">
            <div className="p-3 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
              {saveError}
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex items-center justify-between">
          <div className="text-sm text-gray-500">
            {hasChanges ? (
              <span className="text-yellow-400">Unsaved changes</span>
            ) : (
              <span>No changes</span>
            )}
          </div>
          <div className="flex space-x-3">
            <button
              onClick={handleClose}
              disabled={saving}
              className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !!yamlError}
              className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50"
            >
              {saving ? 'Saving...' : isNewLoop ? 'Create Loop' : 'Save Changes'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
