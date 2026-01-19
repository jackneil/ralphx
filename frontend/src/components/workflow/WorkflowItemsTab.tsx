import { useState, useEffect, useCallback } from 'react'
import { listItems, createItem, updateItem, duplicateItem, Item, getStatusDisplayName, getStatusColor } from '../../api'
import WorkItemRow from './WorkItemRow'
import ItemEditModal, { ItemFormData } from './ItemEditModal'

interface WorkflowItemsTabProps {
  projectSlug: string
  workflowId: string
  sourceStepId?: number  // Optional: pre-filter to a specific step
}

const ITEMS_PER_PAGE = 50

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'pending', label: 'Queued' },
  { value: 'completed', label: 'Ready' },
  { value: 'claimed', label: 'In Progress' },
  { value: 'processed', label: 'Done' },
  { value: 'failed', label: 'Failed' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'duplicate', label: 'Duplicate' },
]

export default function WorkflowItemsTab({ projectSlug, workflowId, sourceStepId }: WorkflowItemsTabProps) {
  const [items, setItems] = useState<Item[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [searchQuery, setSearchQuery] = useState('')

  // Pagination
  const [page, setPage] = useState(0)

  // Available categories (extracted from items)
  const [categories, setCategories] = useState<string[]>([])

  // Modal state
  const [modalOpen, setModalOpen] = useState(false)
  const [modalMode, setModalMode] = useState<'create' | 'edit' | 'duplicate'>('create')
  const [editingItem, setEditingItem] = useState<Item | null>(null)

  const loadItems = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await listItems(projectSlug, {
        workflow_id: workflowId,
        source_step_id: sourceStepId,
        status: statusFilter || undefined,
        category: categoryFilter || undefined,
        limit: ITEMS_PER_PAGE,
        offset: page * ITEMS_PER_PAGE,
      })
      setItems(result.items)
      setTotal(result.total)

      // Extract unique categories from first batch (if page 0)
      if (page === 0 && result.items.length > 0) {
        const uniqueCategories = [...new Set(result.items.map(i => i.category).filter(Boolean) as string[])]
        setCategories(uniqueCategories.sort())
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load items')
    } finally {
      setLoading(false)
    }
  }, [projectSlug, workflowId, sourceStepId, statusFilter, categoryFilter, page])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  // Reset to first page when filters change
  useEffect(() => {
    setPage(0)
  }, [statusFilter, categoryFilter])

  // Modal handlers
  const handleAddItem = () => {
    setEditingItem(null)
    setModalMode('create')
    setModalOpen(true)
  }

  const handleEditItem = (item: Item) => {
    setEditingItem(item)
    setModalMode('edit')
    setModalOpen(true)
  }

  const handleDuplicateItem = (item: Item) => {
    setEditingItem(item)
    setModalMode('duplicate')
    setModalOpen(true)
  }

  const handleSaveItem = async (data: ItemFormData) => {
    // Determine the source step ID to use
    const stepId = editingItem?.source_step_id || sourceStepId || 0

    if (modalMode === 'create') {
      await createItem(projectSlug, {
        workflow_id: workflowId,
        source_step_id: stepId,
        title: data.title || undefined,
        content: data.content,
        category: data.category || undefined,
        priority: data.priority || undefined,
        dependencies: data.dependencies.length > 0 ? data.dependencies : undefined,
      })
    } else if (modalMode === 'edit' && editingItem) {
      await updateItem(projectSlug, editingItem.id, {
        title: data.title || undefined,
        content: data.content,
        category: data.category || undefined,
        priority: data.priority,
        dependencies: data.dependencies,
      })
    } else if (modalMode === 'duplicate' && editingItem) {
      await duplicateItem(projectSlug, editingItem.id, {
        title: data.title || undefined,
        content: data.content,
        category: data.category || undefined,
        priority: data.priority,
        dependencies: data.dependencies.length > 0 ? data.dependencies : undefined,
      })
    }

    // Reload items after save
    loadItems()
  }

  // Filter items by search query (client-side)
  const filteredItems = searchQuery
    ? items.filter(item =>
        (item.title?.toLowerCase().includes(searchQuery.toLowerCase())) ||
        item.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.id.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : items

  const totalPages = Math.ceil(total / ITEMS_PER_PAGE)

  // Status breakdown
  const statusCounts = items.reduce((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1
    return acc
  }, {} as Record<string, number>)

  return (
    <div className="space-y-4">
      {/* Header with counts */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
            Work Items
          </h3>
          <span className="text-sm text-[var(--color-text-muted)]">
            {total} total
          </span>
          {/* Add Item button */}
          <button
            onClick={handleAddItem}
            className="px-3 py-1.5 text-sm font-medium bg-cyan-600 hover:bg-cyan-500 text-white rounded transition-colors"
          >
            + Add Item
          </button>
        </div>

        {/* Status pills */}
        <div className="flex items-center gap-2">
          {Object.entries(statusCounts).map(([status, count]) => (
            <button
              key={status}
              onClick={() => setStatusFilter(statusFilter === status ? '' : status)}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors
                ${statusFilter === status ? 'ring-2 ring-offset-1 ring-offset-[var(--color-surface)]' : ''}
                ${getStatusColor(status)}`}
            >
              <span>{getStatusDisplayName(status)}</span>
              <span className="opacity-75">{count}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 flex-wrap">
        {/* Search */}
        <div className="flex-1 min-w-[200px] max-w-md">
          <input
            type="text"
            placeholder="Search by title, content, or ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full px-3 py-2 text-sm bg-[var(--color-elevated)] border border-[var(--color-border)] rounded-lg
                     text-[var(--color-text-primary)] placeholder-[var(--color-text-muted)]
                     focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
          />
        </div>

        {/* Status Filter */}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-2 text-sm bg-[var(--color-elevated)] border border-[var(--color-border)] rounded-lg
                   text-[var(--color-text-primary)]
                   focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
        >
          {STATUS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>

        {/* Category Filter */}
        {categories.length > 0 && (
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-3 py-2 text-sm bg-[var(--color-elevated)] border border-[var(--color-border)] rounded-lg
                     text-[var(--color-text-primary)]
                     focus:outline-none focus:ring-2 focus:ring-cyan-500/50"
          >
            <option value="">All Categories</option>
            {categories.map(cat => (
              <option key={cat} value={cat}>{cat.toUpperCase()}</option>
            ))}
          </select>
        )}

        {/* Clear Filters */}
        {(statusFilter || categoryFilter || searchQuery) && (
          <button
            onClick={() => {
              setStatusFilter('')
              setCategoryFilter('')
              setSearchQuery('')
            }}
            className="px-3 py-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)] transition-colors"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="p-4 bg-red-900/20 border border-red-800 rounded-lg text-red-400">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="py-8 text-center text-[var(--color-text-muted)]">
          Loading items...
        </div>
      )}

      {/* Table */}
      {!loading && filteredItems.length > 0 && (
        <div className="bg-[var(--color-elevated)] border border-[var(--color-border)] rounded-lg overflow-hidden">
          {/* Table Header */}
          <div className="flex items-center gap-4 px-4 py-3 bg-[var(--color-surface)] border-b border-[var(--color-border)] text-xs font-medium text-[var(--color-text-muted)] uppercase tracking-wide">
            <div className="w-24 flex-shrink-0">ID</div>
            <div className="flex-1">Title</div>
            <div className="w-28 flex-shrink-0">Status</div>
            <div className="w-20 flex-shrink-0">Category</div>
            <div className="w-20 flex-shrink-0 text-right">Created</div>
            <div className="w-6 flex-shrink-0"></div>
          </div>

          {/* Rows */}
          {filteredItems.map(item => (
            <WorkItemRow
              key={item.id}
              projectSlug={projectSlug}
              item={item}
              onUpdate={loadItems}
              onEdit={handleEditItem}
              onDuplicate={handleDuplicateItem}
            />
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && filteredItems.length === 0 && (
        <div className="py-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[var(--color-elevated)] flex items-center justify-center">
            <svg className="w-8 h-8 text-[var(--color-text-muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <p className="text-[var(--color-text-muted)]">
            {(statusFilter || categoryFilter || searchQuery)
              ? 'No items match your filters'
              : 'No work items yet'}
          </p>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between pt-4">
          <div className="text-sm text-[var(--color-text-muted)]">
            Showing {page * ITEMS_PER_PAGE + 1}-{Math.min((page + 1) * ITEMS_PER_PAGE, total)} of {total}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 text-sm bg-[var(--color-elevated)] border border-[var(--color-border)] rounded
                       text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)]
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <span className="text-sm text-[var(--color-text-muted)]">
              Page {page + 1} of {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 text-sm bg-[var(--color-elevated)] border border-[var(--color-border)] rounded
                       text-[var(--color-text-secondary)] hover:bg-[var(--color-surface)]
                       disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Item Edit Modal */}
      <ItemEditModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        onSave={handleSaveItem}
        item={editingItem}
        mode={modalMode}
        workflowId={workflowId}
        sourceStepId={sourceStepId || 0}
        existingCategories={categories}
      />
    </div>
  )
}
