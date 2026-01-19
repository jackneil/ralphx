import { useState, useEffect } from 'react'
import type { Item } from '../../api'

interface ItemEditModalProps {
  isOpen: boolean
  onClose: () => void
  onSave: (data: ItemFormData) => Promise<void>
  item?: Item | null // null = create new, Item = edit existing
  mode: 'create' | 'edit' | 'duplicate'
  workflowId: string
  sourceStepId: number
  existingCategories?: string[]
}

export interface ItemFormData {
  title: string
  content: string
  category: string
  priority: number
  dependencies: string[]
}

const DEFAULT_FORM: ItemFormData = {
  title: '',
  content: '',
  category: '',
  priority: 0,
  dependencies: [],
}

export default function ItemEditModal({
  isOpen,
  onClose,
  onSave,
  item,
  mode,
  existingCategories = [],
}: ItemEditModalProps) {
  const [form, setForm] = useState<ItemFormData>(DEFAULT_FORM)
  const [dependencyInput, setDependencyInput] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Reset form when modal opens or item changes
  useEffect(() => {
    if (isOpen) {
      if (item && (mode === 'edit' || mode === 'duplicate')) {
        setForm({
          title: mode === 'duplicate' && item.title
            ? `${item.title} (copy)`
            : item.title || '',
          content: item.content,
          category: item.category || '',
          priority: item.priority || 0,
          dependencies: item.dependencies || [],
        })
      } else {
        setForm(DEFAULT_FORM)
      }
      setDependencyInput('')
      setError(null)
    }
  }, [isOpen, item, mode])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)

    // Validation
    if (!form.content.trim()) {
      setError('Content is required')
      return
    }

    setSaving(true)
    try {
      await onSave(form)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save')
    } finally {
      setSaving(false)
    }
  }

  const addDependency = () => {
    const dep = dependencyInput.trim().toUpperCase()
    if (dep && !form.dependencies.includes(dep)) {
      setForm(prev => ({
        ...prev,
        dependencies: [...prev.dependencies, dep],
      }))
      setDependencyInput('')
    }
  }

  const removeDependency = (dep: string) => {
    setForm(prev => ({
      ...prev,
      dependencies: prev.dependencies.filter(d => d !== dep),
    }))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addDependency()
    }
  }

  if (!isOpen) return null

  const title = mode === 'create'
    ? 'Create New Item'
    : mode === 'duplicate'
    ? 'Duplicate Item'
    : 'Edit Item'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-[var(--color-elevated)] border border-[var(--color-border)] rounded-lg shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border)]">
          <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
            {title}
          </h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-[var(--color-border)] rounded transition-colors"
          >
            <svg className="w-5 h-5 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {error && (
            <div className="p-3 bg-red-500/10 border border-red-500/20 rounded text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
              Title (optional)
            </label>
            <input
              type="text"
              value={form.title}
              onChange={e => setForm(prev => ({ ...prev, title: e.target.value }))}
              className="w-full px-3 py-2 bg-[var(--color-base)] border border-[var(--color-border)] rounded
                text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)]
                focus:outline-none focus:border-cyan-500"
              placeholder="e.g., FND-001: Add user authentication"
            />
          </div>

          {/* Content */}
          <div>
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
              Content <span className="text-red-400">*</span>
            </label>
            <textarea
              value={form.content}
              onChange={e => setForm(prev => ({ ...prev, content: e.target.value }))}
              rows={8}
              className="w-full px-3 py-2 bg-[var(--color-base)] border border-[var(--color-border)] rounded
                text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)] font-mono text-sm
                focus:outline-none focus:border-cyan-500 resize-y"
              placeholder="Describe the work item..."
              required
            />
          </div>

          {/* Category and Priority row */}
          <div className="grid grid-cols-2 gap-4">
            {/* Category */}
            <div>
              <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                Category
              </label>
              <input
                type="text"
                list="categories"
                value={form.category}
                onChange={e => setForm(prev => ({ ...prev, category: e.target.value }))}
                className="w-full px-3 py-2 bg-[var(--color-base)] border border-[var(--color-border)] rounded
                  text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)]
                  focus:outline-none focus:border-cyan-500"
                placeholder="e.g., FND, API, UI"
              />
              <datalist id="categories">
                {existingCategories.map(cat => (
                  <option key={cat} value={cat} />
                ))}
              </datalist>
            </div>

            {/* Priority */}
            <div>
              <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
                Priority
              </label>
              <input
                type="number"
                value={form.priority}
                onChange={e => setForm(prev => ({ ...prev, priority: parseInt(e.target.value) || 0 }))}
                min={0}
                max={100}
                className="w-full px-3 py-2 bg-[var(--color-base)] border border-[var(--color-border)] rounded
                  text-[var(--color-text-primary)]
                  focus:outline-none focus:border-cyan-500"
              />
              <p className="text-xs text-[var(--color-text-muted)] mt-1">0 = lowest, 100 = highest</p>
            </div>
          </div>

          {/* Dependencies */}
          <div>
            <label className="block text-sm font-medium text-[var(--color-text-secondary)] mb-1">
              Dependencies
            </label>
            <div className="flex gap-2 mb-2">
              <input
                type="text"
                value={dependencyInput}
                onChange={e => setDependencyInput(e.target.value)}
                onKeyDown={handleKeyDown}
                className="flex-1 px-3 py-2 bg-[var(--color-base)] border border-[var(--color-border)] rounded
                  text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)]
                  focus:outline-none focus:border-cyan-500"
                placeholder="e.g., FND-001"
              />
              <button
                type="button"
                onClick={addDependency}
                className="px-3 py-2 bg-[var(--color-border)] hover:bg-[var(--color-border-hover)] rounded
                  text-[var(--color-text-secondary)] transition-colors"
              >
                Add
              </button>
            </div>
            {form.dependencies.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {form.dependencies.map(dep => (
                  <span
                    key={dep}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-sm"
                  >
                    {dep}
                    <button
                      type="button"
                      onClick={() => removeDependency(dep)}
                      className="hover:text-blue-200"
                    >
                      <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4 border-t border-[var(--color-border)]">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]
                hover:bg-[var(--color-border)] rounded transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded
                transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving...' : mode === 'create' ? 'Create' : mode === 'duplicate' ? 'Duplicate' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
