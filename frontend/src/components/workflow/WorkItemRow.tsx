import { useState } from 'react'
import { Item, getStatusDisplayName, getStatusColor, updateItem, deleteItem } from '../../api'
import { formatRelativeTime, formatLocalFull } from '../../utils/time'

interface WorkItemRowProps {
  projectSlug: string
  item: Item
  onUpdate: () => void
  onEdit?: (item: Item) => void
  onDuplicate?: (item: Item) => void
}

export default function WorkItemRow({ projectSlug, item, onUpdate, onEdit, onDuplicate }: WorkItemRowProps) {
  const [expanded, setExpanded] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [actionsEnabled, setActionsEnabled] = useState(false)

  const handleStatusChange = async (newStatus: string) => {
    setUpdating(true)
    setError(null)
    try {
      await updateItem(projectSlug, item.id, { status: newStatus })
      onUpdate()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update item')
    } finally {
      setUpdating(false)
    }
  }

  const handleDelete = async () => {
    if (!window.confirm('Are you sure you want to delete this item?')) return
    setUpdating(true)
    setError(null)
    try {
      await deleteItem(projectSlug, item.id)
      onUpdate()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete item')
    } finally {
      setUpdating(false)
    }
  }

  // Extract short ID (first part before hyphen or first 8 chars)
  const shortId = item.id.includes('-')
    ? item.id.split('-')[0].toUpperCase() + '-' + item.id.split('-')[1]?.slice(0, 3).toUpperCase()
    : item.id.slice(0, 8).toUpperCase()

  return (
    <div className="border-b border-[var(--color-border)] last:border-b-0">
      {/* Compact Row */}
      <div
        className={`flex items-center gap-4 px-4 py-3 cursor-pointer hover:bg-[var(--color-elevated)] transition-colors ${expanded ? 'bg-[var(--color-elevated)]' : ''}`}
        onClick={() => {
          if (expanded) setActionsEnabled(false) // Reset actions when collapsing
          setExpanded(!expanded)
        }}
      >
        {/* ID */}
        <div className="w-24 flex-shrink-0">
          <span className="font-mono text-xs text-[var(--color-text-muted)]">
            {shortId}
          </span>
        </div>

        {/* Title */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-[var(--color-text-primary)] truncate">
            {item.title || item.content.slice(0, 80)}
          </p>
        </div>

        {/* Status Badge */}
        <div className="w-28 flex-shrink-0">
          <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(item.status)}`}>
            {getStatusDisplayName(item.status)}
          </span>
        </div>

        {/* Category */}
        <div className="w-20 flex-shrink-0">
          {item.category && (
            <span className="text-xs text-[var(--color-text-muted)] uppercase">
              {item.category}
            </span>
          )}
        </div>

        {/* Created */}
        <div className="w-20 flex-shrink-0 text-right">
          <span className="text-xs text-[var(--color-text-muted)]">
            {formatRelativeTime(item.created_at)}
          </span>
        </div>

        {/* Expand Icon */}
        <div className="w-6 flex-shrink-0">
          <svg
            className={`w-4 h-4 text-[var(--color-text-muted)] transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {/* Expanded Details */}
      {expanded && (
        <div className="px-4 py-4 bg-[var(--color-surface)] border-t border-[var(--color-border)]">
          {/* Full Content */}
          <div className="mb-4">
            <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-2 uppercase tracking-wide">
              Content
            </h4>
            <p className="text-sm text-[var(--color-text-secondary)] whitespace-pre-wrap">
              {item.content}
            </p>
          </div>

          {/* Dependencies */}
          {item.dependencies && item.dependencies.length > 0 && (
            <div className="mb-4">
              <h4 className="text-xs font-medium text-[var(--color-text-muted)] mb-2 uppercase tracking-wide">
                Dependencies
              </h4>
              <div className="flex flex-wrap gap-1">
                {item.dependencies.map((dep) => (
                  <span
                    key={dep}
                    className="text-xs px-2 py-0.5 rounded bg-[var(--color-elevated)] text-[var(--color-text-secondary)]"
                  >
                    {dep}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-xs">
            <div>
              <span className="text-[var(--color-text-muted)]">Created:</span>
              <span className="ml-1 text-[var(--color-text-secondary)]">{formatLocalFull(item.created_at)}</span>
            </div>
            <div>
              <span className="text-[var(--color-text-muted)]">Updated:</span>
              <span className="ml-1 text-[var(--color-text-secondary)]">{formatLocalFull(item.updated_at)}</span>
            </div>
            {item.phase !== undefined && (
              <div>
                <span className="text-[var(--color-text-muted)]">Phase:</span>
                <span className="ml-1 text-[var(--color-text-secondary)]">{item.phase}</span>
              </div>
            )}
            {item.priority !== undefined && item.priority > 0 && (
              <div>
                <span className="text-[var(--color-text-muted)]">Priority:</span>
                <span className="ml-1 text-[var(--color-text-secondary)]">P{item.priority}</span>
              </div>
            )}
            {item.claimed_by && (
              <div>
                <span className="text-[var(--color-text-muted)]">Claimed by:</span>
                <span className="ml-1 text-[var(--color-text-secondary)]">{item.claimed_by}</span>
              </div>
            )}
            {item.duplicate_of && (
              <div>
                <span className="text-[var(--color-text-muted)]">Duplicate of:</span>
                <span className="ml-1 text-[var(--color-text-secondary)]">{item.duplicate_of}</span>
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 px-3 py-2 bg-red-900/30 border border-red-800 rounded text-xs text-red-400" role="alert">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2">
            {!actionsEnabled ? (
              <button
                onClick={(e) => { e.stopPropagation(); setActionsEnabled(true); }}
                className="px-3 py-1.5 text-xs rounded border border-[var(--color-border)] text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] hover:border-[var(--color-border-hover)] transition-colors"
              >
                Enable Actions
              </button>
            ) : (
              <>
                {/* Edit & Duplicate */}
                {onEdit && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onEdit(item); }}
                    disabled={updating}
                    className="px-3 py-1.5 text-xs rounded bg-cyan-600/20 text-cyan-400 hover:bg-cyan-600/30 disabled:opacity-50 transition-colors"
                  >
                    Edit
                  </button>
                )}
                {onDuplicate && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onDuplicate(item); }}
                    disabled={updating}
                    className="px-3 py-1.5 text-xs rounded bg-purple-600/20 text-purple-400 hover:bg-purple-600/30 disabled:opacity-50 transition-colors"
                  >
                    Duplicate
                  </button>
                )}

                {/* Divider */}
                <div className="w-px h-6 bg-[var(--color-border)] self-center mx-1" />

                {/* Status Changes */}
                {item.status !== 'processed' && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleStatusChange('processed'); }}
                    disabled={updating}
                    className="px-3 py-1.5 text-xs rounded bg-green-600/20 text-green-400 hover:bg-green-600/30 disabled:opacity-50 transition-colors"
                  >
                    Mark Done
                  </button>
                )}
                {item.status !== 'skipped' && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleStatusChange('skipped'); }}
                    disabled={updating}
                    className="px-3 py-1.5 text-xs rounded bg-gray-600/20 text-gray-400 hover:bg-gray-600/30 disabled:opacity-50 transition-colors"
                  >
                    Skip
                  </button>
                )}
                {item.status !== 'pending' && (
                  <button
                    onClick={(e) => { e.stopPropagation(); handleStatusChange('pending'); }}
                    disabled={updating}
                    className="px-3 py-1.5 text-xs rounded bg-blue-600/20 text-blue-400 hover:bg-blue-600/30 disabled:opacity-50 transition-colors"
                  >
                    Reset to Queued
                  </button>
                )}
                <button
                  onClick={(e) => { e.stopPropagation(); handleDelete(); }}
                  disabled={updating}
                  className="px-3 py-1.5 text-xs rounded bg-red-600/20 text-red-400 hover:bg-red-600/30 disabled:opacity-50 transition-colors"
                >
                  Delete
                </button>

                {/* Divider */}
                <div className="w-px h-6 bg-[var(--color-border)] self-center mx-1" />

                {/* Disable actions */}
                <button
                  onClick={(e) => { e.stopPropagation(); setActionsEnabled(false); }}
                  className="px-2 py-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text-secondary)] transition-colors"
                  title="Hide actions"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
