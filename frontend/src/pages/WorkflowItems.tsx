import { useEffect, useState, useCallback } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getProject,
  getWorkflow,
  listItems,
  createItem,
  Item,
  Workflow,
} from '../api'
import { useDashboardStore } from '../stores/dashboard'
import WorkItemCard from '../components/WorkItemCard'
import WorkItemFilters from '../components/WorkItemFilters'

export default function WorkflowItems() {
  const { slug, workflowId } = useParams<{ slug: string; workflowId: string }>()
  const { selectedProject, setSelectedProject } = useDashboardStore()

  const [workflow, setWorkflow] = useState<Workflow | null>(null)
  const [items, setItems] = useState<Item[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [categories, setCategories] = useState<string[]>([])

  // Pagination
  const [offset, setOffset] = useState(0)
  const limit = 20

  // Add Item
  const [showAddForm, setShowAddForm] = useState(false)
  const [newContent, setNewContent] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [addingItem, setAddingItem] = useState(false)

  const loadItems = useCallback(async () => {
    if (!slug || !workflowId) return
    setLoading(true)
    setError(null)

    try {
      const result = await listItems(slug, {
        status: statusFilter === 'all' ? undefined : statusFilter,
        category: categoryFilter || undefined,
        workflow_id: workflowId,
        limit,
        offset,
      })
      setItems(result.items)
      setTotal(result.total)

      // Extract categories from items
      const cats = new Set<string>()
      result.items.forEach(item => {
        if (item.category) cats.add(item.category)
      })
      setCategories(Array.from(cats).sort())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load items')
    } finally {
      setLoading(false)
    }
  }, [slug, workflowId, statusFilter, categoryFilter, offset])

  useEffect(() => {
    async function loadData() {
      if (!slug || !workflowId) return

      try {
        const [projectData, workflowData] = await Promise.all([
          getProject(slug),
          getWorkflow(slug, workflowId),
        ])
        setSelectedProject(projectData)
        setWorkflow(workflowData)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data')
      }
    }

    loadData()
  }, [slug, workflowId, setSelectedProject])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!slug || !workflowId || !workflow || !newContent.trim()) return

    // Find the current step to use as source_step_id
    const currentStep = workflow.steps.find(s => s.step_number === workflow.current_step)
    if (!currentStep) {
      setError('No active workflow step found. Cannot add items.')
      return
    }

    setAddingItem(true)
    try {
      await createItem(slug, {
        content: newContent.trim(),
        workflow_id: workflowId,
        source_step_id: currentStep.id,
        category: newCategory.trim() || undefined,
      })
      setNewContent('')
      setNewCategory('')
      setShowAddForm(false)
      loadItems()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add item')
    } finally {
      setAddingItem(false)
    }
  }

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  // Calculate stats
  const stats = {
    total: total,
    pending: items.filter(i => i.status === 'pending').length,
    in_progress: items.filter(i => i.status === 'in_progress').length,
    completed: items.filter(i => i.status === 'completed').length,
  }

  // Progress percentage
  const progress = total > 0 ? Math.round((stats.completed / total) * 100) : 0

  if (loading && !workflow) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading...</div>
      </div>
    )
  }

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
        <Link to="/" className="hover:text-white">Dashboard</Link>
        <span>/</span>
        <Link to={`/projects/${slug}`} className="hover:text-white">
          {selectedProject?.name || slug}
        </Link>
        <span>/</span>
        <Link to={`/projects/${slug}/workflows/${workflowId}`} className="hover:text-white">
          {workflow?.name || 'Workflow'}
        </Link>
        <span>/</span>
        <span className="text-white">Work Items</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white mb-1">Work Items</h1>
          <p className="text-gray-400">
            {total} item{total !== 1 ? 's' : ''} in this workflow
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>Add Item</span>
        </button>
      </div>

      {/* Stats Bar */}
      <div className="card mb-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center space-x-6 text-sm">
            <span className="text-gray-400">{total} total</span>
            <span className="text-gray-600">|</span>
            <span className="text-green-400">{stats.completed} completed</span>
            <span className="text-gray-600">|</span>
            <span className="text-yellow-400">{stats.in_progress} in progress</span>
            <span className="text-gray-600">|</span>
            <span className="text-gray-400">{stats.pending} pending</span>
          </div>
          <span className="text-sm text-gray-400">{progress}%</span>
        </div>
        <div className="w-full bg-gray-700 rounded-full h-2">
          <div
            className="bg-green-500 h-2 rounded-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Add Item Form */}
      {showAddForm && (
        <div className="card mb-6">
          <h3 className="text-lg font-semibold text-white mb-4">Add New Item</h3>
          <form onSubmit={handleAddItem} className="space-y-4">
            <div>
              <label htmlFor="new-content" className="block text-sm font-medium text-gray-300 mb-1">
                Content
              </label>
              <textarea
                id="new-content"
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="Item content..."
                rows={3}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
              />
            </div>
            <div>
              <label htmlFor="new-category" className="block text-sm font-medium text-gray-300 mb-1">
                Category (optional)
              </label>
              <input
                id="new-category"
                type="text"
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value)}
                placeholder="e.g., FND, API, UI"
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
              />
            </div>
            <div className="flex justify-end space-x-3">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={addingItem || !newContent.trim()}
                className="px-4 py-2 text-sm rounded bg-primary-600 text-white hover:bg-primary-500 disabled:opacity-50"
              >
                {addingItem ? 'Adding...' : 'Add Item'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Filters */}
      <div className="mb-4">
        <WorkItemFilters
          status={statusFilter}
          category={categoryFilter}
          categories={categories}
          onStatusChange={(s) => { setStatusFilter(s); setOffset(0) }}
          onCategoryChange={(c) => { setCategoryFilter(c); setOffset(0) }}
        />
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-red-400" role="alert">
          {error}
        </div>
      )}

      {/* Items */}
      {loading ? (
        <div className="text-gray-400" aria-live="polite">Loading items...</div>
      ) : items.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-gray-400">No items found</p>
          {(statusFilter !== 'all' || categoryFilter) && (
            <p className="text-sm text-gray-500 mt-2">
              Try changing your filters
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <WorkItemCard
              key={item.id}
              projectSlug={slug!}
              item={item}
              onUpdate={loadItems}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <nav className="mt-6 flex items-center justify-between" aria-label="Pagination">
          <div className="text-sm text-gray-400">
            Showing {offset + 1}-{Math.min(offset + limit, total)} of {total}
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setOffset(Math.max(0, offset - limit))}
              disabled={offset === 0}
              className="px-3 py-1 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-50"
              aria-label="Previous page"
            >
              Previous
            </button>
            <span className="text-sm text-gray-400" aria-current="page">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setOffset(offset + limit)}
              disabled={offset + limit >= total}
              className="px-3 py-1 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600 disabled:opacity-50"
              aria-label="Next page"
            >
              Next
            </button>
          </div>
        </nav>
      )}
    </div>
  )
}
