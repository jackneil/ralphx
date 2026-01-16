import { useEffect } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useDashboardStore } from '../stores/dashboard'

export default function Sidebar() {
  const { slug } = useParams()
  const {
    projects,
    projectsLoading,
    projectsError,
    loadProjects,
  } = useDashboardStore()

  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  return (
    <aside className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <Link to="/" className="flex items-center space-x-2">
          <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold">R</span>
          </div>
          <span className="text-xl font-semibold text-white">RalphX</span>
        </Link>
      </div>

      {/* Projects List */}
      <nav className="flex-1 overflow-y-auto p-4">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
          Projects
        </h3>

        {projectsLoading && (
          <div className="text-gray-400 text-sm">Loading...</div>
        )}

        {projectsError && (
          <div className="text-red-400 text-sm">{projectsError}</div>
        )}

        {!projectsLoading && !projectsError && projects.length === 0 && (
          <div className="text-gray-500 text-sm">No projects yet</div>
        )}

        <ul className="space-y-1">
          {projects.map((project) => (
            <li key={project.slug}>
              <Link
                to={`/projects/${project.slug}`}
                className={`block px-3 py-2 rounded-md text-sm transition-colors ${
                  slug === project.slug
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                }`}
              >
                <div className="font-medium">{project.name}</div>
                <div className="text-xs text-gray-400 truncate">{project.path}</div>
              </Link>
            </li>
          ))}
        </ul>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-700 space-y-2">
        <Link
          to="/logs"
          className="flex items-center space-x-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <span>Activity Log</span>
        </Link>
        <Link
          to="/settings"
          className="flex items-center space-x-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <span>Settings</span>
        </Link>
      </div>
    </aside>
  )
}
