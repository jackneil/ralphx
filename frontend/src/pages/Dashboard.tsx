import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useDashboardStore } from '../stores/dashboard'
import { getHealth } from '../api'
import AddProjectDialog from '../components/AddProjectDialog'
import { GettingStarted, EmptyState, EMPTY_STATE_ICONS } from '../components/Help'
import { formatLocalDate } from '../utils/time'

export default function Dashboard() {
  const { projects, projectsLoading, projectsError, loadProjects } = useDashboardStore()
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null)
  const [healthError, setHealthError] = useState(false)
  const [showAddProject, setShowAddProject] = useState(false)

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => {
        setHealth(null)
        setHealthError(true)
      })
  }, [])

  return (
    <div className="p-6">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">Dashboard</h1>
        <p className="text-gray-400">
          Manage your RalphX projects and workflows
        </p>
      </div>

      {/* Health Status */}
      {healthError && !health && (
        <div className="card mb-6 bg-red-900/20 border border-red-800" role="alert">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-red-400">API Unavailable</h2>
              <p className="text-sm text-gray-400">Unable to connect to the backend API</p>
            </div>
            <div className="flex items-center space-x-4">
              <span className="text-sm text-red-400">offline</span>
            </div>
          </div>
        </div>
      )}
      {health && (
        <div className="card mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white">API Status</h2>
              <p className="text-sm text-gray-400">Backend health check</p>
            </div>
            <div className="flex items-center space-x-4">
              <span className={`text-sm ${health.status === 'healthy' ? 'text-green-400' : 'text-red-400'}`}>
                {health.status}
              </span>
              <span className="text-sm text-gray-500">v{health.version}</span>
            </div>
          </div>
        </div>
      )}

      {/* Getting Started (shows for new users) */}
      <GettingStarted />

      {/* Add Project Dialog */}
      {showAddProject && (
        <AddProjectDialog
          onClose={() => setShowAddProject(false)}
          onSuccess={() => loadProjects()}
        />
      )}

      {/* Projects Grid */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Projects</h2>
          <button
            onClick={() => setShowAddProject(true)}
            className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Add Project</span>
          </button>
        </div>

        {projectsLoading ? (
          <div className="text-gray-400" aria-live="polite">Loading projects...</div>
        ) : projectsError ? (
          <div className="card bg-red-900/20 border border-red-800" role="alert">
            <p className="text-red-400 mb-2">{projectsError}</p>
            <p className="text-sm text-gray-400">
              Unable to load projects. Check that the API is running.
            </p>
          </div>
        ) : projects.length === 0 ? (
          <div className="card">
            <EmptyState
              icon={EMPTY_STATE_ICONS.folder}
              title="No projects yet"
              description="Create your first project to start building AI-powered development workflows."
              action={{
                label: 'Add Project',
                onClick: () => setShowAddProject(true),
              }}
            >
              <p className="text-xs text-gray-500 mt-4">
                Or use the CLI: <code className="bg-gray-700 px-2 py-1 rounded">ralphx add /path/to/project</code>
              </p>
            </EmptyState>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project) => (
              <Link
                key={project.slug}
                to={`/projects/${project.slug}`}
                className="card hover:bg-gray-700 transition-colors"
              >
                <h3 className="text-lg font-semibold text-white mb-2">
                  {project.name}
                </h3>
                <p className="text-sm text-gray-400 truncate mb-3">
                  {project.path}
                </p>
                <div className="text-xs text-gray-500">
                  Added: {formatLocalDate(project.created_at)}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card">
          <div className="text-3xl font-bold text-primary-400">{projects.length}</div>
          <div className="text-sm text-gray-400">Total Projects</div>
        </div>
        <div className="card">
          <div className="text-3xl font-bold text-green-400">0</div>
          <div className="text-sm text-gray-400">Active Workflows</div>
        </div>
        <div className="card">
          <div className="text-3xl font-bold text-yellow-400">0</div>
          <div className="text-sm text-gray-400">Pending Items</div>
        </div>
      </div>
    </div>
  )
}
