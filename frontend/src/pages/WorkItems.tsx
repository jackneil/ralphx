import { useEffect, useState, useCallback, useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { listItems, getItemsStats, getProject, listLoops, Item, ItemTypes } from '../api'
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
  const [searchParams] = useSearchParams()
  const { selectedProject, setSelectedProject } = useDashboardStore()

  const [items, setItems] = useState<Item[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Loop terminology mapping (reserved for future use)
  const [_loopTerminology, setLoopTerminology] = useState<Map<string, ItemTypes>>(new Map())
  const [_availableLoops, setAvailableLoops] = useState<string[]>([])

  // Filters
  const [statusFilter, setStatusFilter] = useState('all')
  const [categoryFilter, setCategoryFilter] = useState('')
  const workflowIdFilter = searchParams.get('workflow_id') || ''
  const [categories, setCategories] = useState<string[]>([])

  // Pagination
  const [offset, setOffset] = useState(0)
  const limit = 20

  // Add Item - Disabled in cross-workflow view (items require workflow context)
  // Use workflow-specific /workflows/{id}/items page to add items

  // Get terminology for current context
  const currentTerminology = useMemo(() => {
    // Use default terminology since we now filter by workflow, not loop
    return DEFAULT_TERMINOLOGY
  }, [])

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
        workflow_id: workflowIdFilter || undefined,
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
  }, [slug, statusFilter, categoryFilter, workflowIdFilter, offset])

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

  // NOTE: Adding items from this cross-workflow view is disabled.
  // Work items require a workflow context (workflow_id and source_step_id).
  // Use the workflow-specific /workflows/{id}/items page to add items.

  const totalPages = Math.ceil(total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  // Dynamic page title
  const pageTitle = workflowIdFilter
    ? `${capitalize(currentTerminology.plural)} from workflow ${workflowIdFilter.slice(0, 8)}`
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
        {/* Add button disabled in cross-workflow view - items require workflow context */}
        <span className="text-sm text-gray-500" title="Use workflow-specific items page to add items">
          Adding items requires workflow context
        </span>
      </div>

      {/* Add Item Form - Disabled in cross-workflow view
          Work items require workflow context. Use /workflows/{id}/items to add items.
      */}

      {/* Filters */}
      <div className="mb-4">
        <WorkItemFilters
          status={statusFilter}
          category={categoryFilter}
          categories={categories}
          onStatusChange={(s) => { setStatusFilter(s); setOffset(0) }}
          onCategoryChange={(c) => { setCategoryFilter(c); setOffset(0) }}
        />

        {/* Workflow Filter - can be added when workflows are available */}
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
          {(statusFilter !== 'all' || categoryFilter || workflowIdFilter) && (
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
