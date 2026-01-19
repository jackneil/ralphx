import { useState } from 'react'
import { updateItem, deleteItem, Item, ItemTypeConfig, getStatusDisplayName, getStatusColor } from '../api'
import { formatLocalFull } from '../utils/time'

interface ItemCardProps {
  projectSlug: string
  item: Item
  onUpdate: () => void
  terminology?: ItemTypeConfig
}

export default function WorkItemCard({ projectSlug, item, onUpdate, terminology }: ItemCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [updating, setUpdating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Get display name for item type
  const itemTypeName = terminology?.singular || item.item_type || 'item'

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

  return (
    <div className="card">
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center flex-wrap gap-2">
          <span className={`text-xs px-2 py-0.5 rounded ${getStatusColor(item.status)}`}>
            {getStatusDisplayName(item.status)}
          </span>
          {item.phase !== undefined && (
            <span className="text-xs px-2 py-0.5 rounded bg-indigo-900 text-indigo-300" title="Phase">
              Phase {item.phase}
            </span>
          )}
          {item.workflow_id && (
            <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-300" title="Workflow ID">
              {item.workflow_id.slice(0, 8)}
            </span>
          )}
          {item.source_step_id && (
            <span className="text-xs px-2 py-0.5 rounded bg-indigo-900/50 text-indigo-300" title="Source step">
              Step {item.source_step_id}
            </span>
          )}
          {item.item_type && item.item_type !== 'item' && (
            <span className="text-xs px-2 py-0.5 rounded bg-primary-900 text-primary-300" title="Item type">
              {itemTypeName}
            </span>
          )}
          {item.category && (
            <span className="text-xs text-gray-400">{item.category.toUpperCase()}</span>
          )}
          {item.priority !== undefined && item.priority > 0 && (
            <span className="text-xs text-primary-400">P{item.priority}</span>
          )}
          {item.dependencies && item.dependencies.length > 0 && (
            <span className="text-xs px-2 py-0.5 rounded bg-gray-700 text-gray-400" title={`Depends on: ${item.dependencies.join(', ')}`}>
              {item.dependencies.length} dep{item.dependencies.length > 1 ? 's' : ''}
            </span>
          )}
          {item.claimed_by && (
            <span className="text-xs px-2 py-0.5 rounded bg-blue-900/50 text-blue-300" title="Claimed by">
              Claimed: {item.claimed_by}
            </span>
          )}
          {item.duplicate_of && (
            <span className="text-xs px-2 py-0.5 rounded bg-orange-900/50 text-orange-300" title="Duplicate of">
              Dup of: {item.duplicate_of}
            </span>
          )}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-gray-400 hover:text-white"
          aria-expanded={expanded}
          aria-label={expanded ? 'Collapse item details' : 'Expand item details'}
        >
          <svg
            className={`w-5 h-5 transition-transform ${expanded ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>

      {/* Title & Content */}
      {item.title && (
        <h4 className="text-sm font-medium text-white mb-1">
          {item.title}
        </h4>
      )}
      <p className={`text-sm text-gray-200 ${expanded ? '' : 'line-clamp-2'}`}>
        {item.content}
      </p>
      {item.skip_reason && (
        <p className="text-xs text-gray-400 mt-1 italic">
          Skip reason: {item.skip_reason}
        </p>
      )}

      {/* Expanded Details */}
      {expanded && (
        <div className="mt-4 pt-4 border-t border-gray-700">
          {/* Dependencies */}
          {item.dependencies && item.dependencies.length > 0 && (
            <div className="mb-4 p-3 bg-gray-700/50 rounded">
              <div className="text-xs font-medium text-gray-400 mb-2">Dependencies</div>
              <div className="flex flex-wrap gap-1">
                {item.dependencies.map((dep) => (
                  <span
                    key={dep}
                    className="text-xs px-2 py-0.5 rounded bg-gray-600 text-gray-300"
                  >
                    {dep}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Metadata */}
          <div className="text-xs text-gray-500 mb-4 space-y-1">
            <div>Created: {formatLocalFull(item.created_at)}</div>
            <div>Updated: {formatLocalFull(item.updated_at)}</div>
            {item.claimed_at && (
              <div>Claimed: {formatLocalFull(item.claimed_at)}</div>
            )}
            {item.processed_at && (
              <div>Processed: {formatLocalFull(item.processed_at)}</div>
            )}
            <div>ID: {item.id}</div>
            {item.workflow_id && <div>Workflow: {item.workflow_id}</div>}
            {item.source_step_id !== undefined && <div>Source Step: {item.source_step_id}</div>}
            {item.item_type && <div>Type: {itemTypeName}</div>}
            {item.phase !== undefined && <div>Phase: {item.phase}</div>}
            {item.duplicate_of && <div>Duplicate of: {item.duplicate_of}</div>}
            {item.skip_reason && <div>Skip reason: {item.skip_reason}</div>}
          </div>

          {/* Error */}
          {error && (
            <div className="mb-3 px-3 py-2 bg-red-900/30 border border-red-800 rounded text-xs text-red-400" role="alert">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex flex-wrap gap-2">
            {item.status !== 'completed' && (
              <button
                onClick={() => handleStatusChange('completed')}
                disabled={updating}
                className="px-3 py-1 text-xs rounded bg-green-800 text-green-200 hover:bg-green-700 disabled:opacity-50"
              >
                Mark Complete
              </button>
            )}
            {item.status !== 'rejected' && (
              <button
                onClick={() => handleStatusChange('rejected')}
                disabled={updating}
                className="px-3 py-1 text-xs rounded bg-red-800 text-red-200 hover:bg-red-700 disabled:opacity-50"
              >
                Reject
              </button>
            )}
            {item.status !== 'pending' && (
              <button
                onClick={() => handleStatusChange('pending')}
                disabled={updating}
                className="px-3 py-1 text-xs rounded bg-yellow-800 text-yellow-200 hover:bg-yellow-700 disabled:opacity-50"
              >
                Reset to Pending
              </button>
            )}
            <button
              onClick={handleDelete}
              disabled={updating}
              className="px-3 py-1 text-xs rounded bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-50"
            >
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
