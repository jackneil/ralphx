interface ItemFiltersProps {
  status: string
  category: string
  categories: string[]
  onStatusChange: (status: string) => void
  onCategoryChange: (category: string) => void
}

// Keeping export name for backward compatibility
export default function WorkItemFilters({
  status,
  category,
  categories,
  onStatusChange,
  onCategoryChange,
}: ItemFiltersProps) {
  const statuses = ['all', 'pending', 'in_progress', 'completed', 'rejected']

  return (
    <div className="flex flex-wrap gap-4 mb-4">
      {/* Status Filter */}
      <div>
        <label className="block text-sm font-medium text-gray-400 mb-1">
          Status
        </label>
        <select
          value={status}
          onChange={(e) => onStatusChange(e.target.value)}
          className="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-primary-500"
        >
          {statuses.map((s) => (
            <option key={s} value={s}>
              {s === 'all' ? 'All Statuses' : s.replace('_', ' ')}
            </option>
          ))}
        </select>
      </div>

      {/* Category Filter */}
      <div>
        <label className="block text-sm font-medium text-gray-400 mb-1">
          Category
        </label>
        <select
          value={category}
          onChange={(e) => onCategoryChange(e.target.value)}
          className="px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white text-sm focus:outline-none focus:border-primary-500"
        >
          <option value="">All Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </div>
    </div>
  )
}
