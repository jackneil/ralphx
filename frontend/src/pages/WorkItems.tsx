import { useEffect, useState, useCallback, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { listItems, getItemsStats, createItem, getProject, listLoops, Item, ItemTypes } from '../api'
import { useDashboardStore } from '../stores/dashboard'
import WorkItemCard from '../components/WorkItemCard'
import WorkItemFilters from '../components/WorkItemFilters'

// Default terminology when no loop context
const DEFAULT_TERMINOLOGY = {
  singular: 'item',
  plural: 'items',
}

// Re-export as Items page (renamed from WorkItems)
export default function Items() {
  const { slug } = useParams<{ slug: string }>()
  const [searchParams, setSearchParams] = useSearchParams()
  const { selectedProject, setSelectedProject } = useDashboardStore()

  const [items, setItems] = useState<Item[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Loop terminology mapping
  const [loopTerminology, setLoopTerminology] = useState<Map<string, ItemTypes>>(new Map())
  const [availableLoops, setAvailableLoops] = useState<string[]>([])

  // Filters
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('')
  const sourceLoopFilter = searchParams.get('source_loop') || ''
  const [categories, setCategories] = useState<string[]>([])

  // Pagination
  const [offset, setOffset] = useState(0)
  const limit = 20

  // Add Item
  const [showAddForm, setShowAddForm] = useState(false)
  const [newContent, setNewContent] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [addingItem, setAddingItem] = useState(false)

  // Get terminology for current context
  const currentTerminology = useMemo(() => {
    if (sourceLoopFilter && loopTerminology.has(sourceLoopFilter)) {
      const terms = loopTerminology.get(sourceLoopFilter)!
      return terms.output || DEFAULT_TERMINOLOGY
    }
    return DEFAULT_TERMINOLOGY
  }, [sourceLoopFilter, loopTerminology])

  // Capitalize first letter helper
  const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

  const loadItems = useCallback(async () => {
    if (!slug) return
    setLoading(true)
    setError(null)
    try {
      const result = await listItems(slug, {
        status: statusFilter === 'all' ? undefined : statusFilter,
        category: categoryFilter || undefined,
        source_loop: sourceLoopFilter || undefined,
        limit,
        offset,
      })
      setItems(result.items)
      setTotal(result.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load items')
    } finally {
      setLoading(false)
    }
  }, [slug, statusFilter, categoryFilter, sourceLoopFilter, offset])

  const loadStats = useCallback(async () => {
    if (!slug) return
    try {
      const stats = await getItemsStats(slug)
      setCategories(Object.keys(stats.by_category))
    } catch {
      // Ignore stats errors
    }
  }, [slug])

  const loadLoops = useCallback(async () => {
    if (!slug) return
    try {
      const loops = await listLoops(slug)
      setAvailableLoops(loops.map((l) => l.name))

      // Build terminology map
      const termMap = new Map<string, ItemTypes>()
      for (const loop of loops) {
        if (loop.item_types) {
          termMap.set(loop.name, loop.item_types)
        }
      }
      setLoopTerminology(termMap)
    } catch {
      // Ignore loop load errors
    }
  }, [slug])

  useEffect(() => {
    if (!slug) return

    async function loadProject() {
      try {
        const project = await getProject(slug!)
        setSelectedProject(project)
      } catch {
        // Ignore project load errors
      }
    }

    loadProject()
    loadStats()
    loadLoops()
  }, [slug, setSelectedProject, loadStats, loadLoops])

  useEffect(() => {
    loadItems()
  }, [loadItems])

  const handleSourceLoopChange = (loop: string) => {
    setOffset(0)
    if (loop) {
      setSearchParams({ source_loop: loop })
    } else {
      setSearchParams({})
    }
  }

  const handleAddItem = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!slug || !newContent.trim()) return

    setAddingItem(true)
    try {
      await createItem(slug, {
        content: newContent.trim(),
        category: newCategory.trim() || undefined,
      })
      setNewContent('')
      setNewCategory('')
      setShowAddForm(false)
      loadItems()
      loadStats()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add item')
    } finally {
      setAddingItem(false)
    }
  }

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  // Dynamic page title
  const pageTitle = sourceLoopFilter
    ? `${capitalize(currentTerminology.plural)} from ${sourceLoopFilter}`
    : 'Items'

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
        <span className="text-white">{pageTitle}</span>
      </div>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-3xl font-bold text-white mb-1">{pageTitle}</h1>
          <p className="text-gray-400">
            {total} total {total === 1 ? currentTerminology.singular : currentTerminology.plural}
          </p>
        </div>
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>Add {capitalize(currentTerminology.singular)}</span>
        </button>
      </div>

      {/* Add Item Form */}
      {showAddForm && (
        <div className="card mb-6">
          <h3 className="text-lg font-semibold text-white mb-4">
            Add New {capitalize(currentTerminology.singular)}
          </h3>
          <form onSubmit={handleAddItem} className="space-y-4">
            <div>
              <label htmlFor="new-content" className="block text-sm font-medium text-gray-300 mb-1">
                Content
              </label>
              <textarea
                id="new-content"
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder={`${capitalize(currentTerminology.singular)} content...`}
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
                placeholder="e.g., bug, feature, docs"
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
                {addingItem ? 'Adding...' : `Add ${capitalize(currentTerminology.singular)}`}
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

        {/* Source Loop Filter */}
        {availableLoops.length > 0 && (
          <div className="mt-3 flex items-center space-x-3">
            <label htmlFor="source-loop-filter" className="text-sm text-gray-400">
              Source Loop:
            </label>
            <select
              id="source-loop-filter"
              value={sourceLoopFilter}
              onChange={(e) => handleSourceLoopChange(e.target.value)}
              className="px-3 py-1.5 text-sm bg-gray-700 border border-gray-600 rounded text-white focus:outline-none focus:border-primary-500"
            >
              <option value="">All Loops</option>
              {availableLoops.map((loop) => {
                const terms = loopTerminology.get(loop)
                const label = terms?.output?.plural
                  ? `${loop} (${terms.output.plural})`
                  : loop
                return (
                  <option key={loop} value={loop}>
                    {label}
                  </option>
                )
              })}
            </select>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-800 rounded text-red-400" role="alert">
          {error}
        </div>
      )}

      {/* Items */}
      {loading ? (
        <div className="text-gray-400" aria-live="polite">Loading {currentTerminology.plural}...</div>
      ) : items.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-gray-400">No {currentTerminology.plural} found</p>
          {(statusFilter !== 'all' || categoryFilter || sourceLoopFilter) && (
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
              terminology={item.source_loop && loopTerminology.has(item.source_loop)
                ? loopTerminology.get(item.source_loop)!.output
                : undefined
              }
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
