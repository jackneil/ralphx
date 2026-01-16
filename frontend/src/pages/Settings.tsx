import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getHealth, listProjects, deleteProject, cleanupProjects, validateAuth, AuthValidationResult } from '../api'
import { useDashboardStore } from '../stores/dashboard'
import AuthPanel from '../components/AuthPanel'

interface Project {
  id: string
  slug: string
  name: string
  path: string
  created_at: string
}

export default function Settings() {
  const { loadProjects } = useDashboardStore()
  const [health, setHealth] = useState<{ status: string; version: string } | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingSlug, setDeletingSlug] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [cleanupResult, setCleanupResult] = useState<{ deleted: string[]; failed: string[]; dry_run: boolean } | null>(null)
  const [cleaningUp, setCleaningUp] = useState(false)
  const [validationResult, setValidationResult] = useState<AuthValidationResult | null>(null)

  useEffect(() => {
    async function load() {
      setLoading(true)
      try {
        const [healthData, projectData] = await Promise.all([
          getHealth().catch(() => null),
          listProjects().catch(() => []),
        ])
        setHealth(healthData)
        setProjects(projectData)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  // Validate credentials (called on mount and after login success)
  const validateCredentials = async () => {
    try {
      const result = await validateAuth()
      setValidationResult(result)
    } catch {
      setValidationResult({ valid: false, error: 'Failed to validate credentials' })
    }
  }

  // Validate credentials on mount
  useEffect(() => {
    validateCredentials()
  }, [])

  const handleDeleteProject = async (slug: string) => {
    if (!window.confirm(`Are you sure you want to remove project "${slug}"? This will not delete any files.`)) {
      return
    }

    setDeletingSlug(slug)
    setDeleteError(null)
    try {
      await deleteProject(slug)
      setProjects(projects.filter(p => p.slug !== slug))
      loadProjects() // Refresh sidebar
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Failed to remove project')
    } finally {
      setDeletingSlug(null)
    }
  }

  const handleCleanup = async (dryRun: boolean) => {
    setCleaningUp(true)
    setCleanupResult(null)
    setDeleteError(null)
    try {
      const result = await cleanupProjects('^e2e-', dryRun)
      setCleanupResult(result)

      // Refresh projects list if any deletions occurred (success or failure means state changed)
      if (!dryRun && (result.deleted.length > 0 || result.failed.length > 0)) {
        const projectData = await listProjects().catch(() => [])
        setProjects(projectData)
        loadProjects() // Refresh sidebar
      }
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Cleanup failed')
    } finally {
      setCleaningUp(false)
    }
  }

  return (
    <div className="p-6">
      {/* Breadcrumb */}
      <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
        <Link to="/" className="hover:text-white">Dashboard</Link>
        <span>/</span>
        <span className="text-white">Settings</span>
      </div>

      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white mb-2">Settings</h1>
        <p className="text-gray-400">Manage RalphX configuration and projects</p>
      </div>

      {loading ? (
        <div className="text-gray-400">Loading...</div>
      ) : (
        <div className="space-y-6">
          {/* System Info */}
          <div className="card">
            <h2 className="text-lg font-semibold text-white mb-4">System Information</h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between py-2 border-b border-gray-700">
                <span className="text-gray-400">API Status</span>
                <span className={`${health?.status === 'healthy' ? 'text-green-400' : 'text-red-400'}`}>
                  {health?.status || 'unavailable'}
                </span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-gray-700">
                <span className="text-gray-400">Version</span>
                <span className="text-white font-mono">{health?.version || '-'}</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-gray-700">
                <span className="text-gray-400">Workspace</span>
                <span className="text-white font-mono text-sm">~/.ralphx</span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-gray-400">Projects Registered</span>
                <span className="text-white">{projects.length}</span>
              </div>
            </div>
          </div>

          {/* Claude Authentication */}
          <AuthPanel validationResult={validationResult} onLoginSuccess={validateCredentials} />

          {/* Cleanup Test Data */}
          <div className="card">
            <h2 className="text-lg font-semibold text-white mb-4">Cleanup Test Data</h2>
            <p className="text-gray-400 text-sm mb-4">
              Remove orphaned test projects (e2e-test-*, e2e-loop-*, e2e-remove-*) left behind by E2E tests.
            </p>
            <div className="flex items-center space-x-3">
              <button
                onClick={() => handleCleanup(true)}
                disabled={cleaningUp}
                className="px-4 py-2 rounded bg-gray-700 text-gray-200 hover:bg-gray-600 disabled:opacity-50"
              >
                {cleaningUp ? 'Scanning...' : 'Preview Cleanup'}
              </button>
              <button
                onClick={() => handleCleanup(false)}
                disabled={cleaningUp}
                className="px-4 py-2 rounded bg-red-800 text-red-200 hover:bg-red-700 disabled:opacity-50"
              >
                {cleaningUp ? 'Cleaning...' : 'Clean Up Now'}
              </button>
            </div>
            {cleanupResult && (
              <div className="mt-4 space-y-2">
                {/* Preview or Deleted */}
                {cleanupResult.deleted.length > 0 && (
                  <div className={`p-3 rounded ${cleanupResult.dry_run ? 'bg-yellow-900/30 border border-yellow-800' : 'bg-green-900/30 border border-green-800'}`}>
                    <div className={`text-sm font-medium ${cleanupResult.dry_run ? 'text-yellow-400' : 'text-green-400'}`}>
                      {cleanupResult.dry_run ? 'Preview (will be deleted):' : 'Deleted:'}
                    </div>
                    <ul className="text-gray-300 text-sm mt-1 font-mono">
                      {cleanupResult.deleted.map(slug => (
                        <li key={slug}>{slug}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Failed deletions */}
                {cleanupResult.failed && cleanupResult.failed.length > 0 && (
                  <div className="p-3 rounded bg-red-900/30 border border-red-800">
                    <div className="text-sm font-medium text-red-400">
                      Failed to delete (check server logs):
                    </div>
                    <ul className="text-gray-300 text-sm mt-1 font-mono">
                      {cleanupResult.failed.map(slug => (
                        <li key={slug}>{slug}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* No matches at all */}
                {cleanupResult.deleted.length === 0 && (!cleanupResult.failed || cleanupResult.failed.length === 0) && (
                  <div className="p-3 rounded bg-gray-800 border border-gray-700">
                    <p className="text-gray-400 text-sm">No matching projects found</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Registered Projects */}
          <div className="card">
            <h2 className="text-lg font-semibold text-white mb-4">Registered Projects</h2>
            {deleteError && (
              <div className="mb-4 px-3 py-2 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
                {deleteError}
              </div>
            )}
            {projects.length === 0 ? (
              <p className="text-gray-400">No projects registered</p>
            ) : (
              <div className="space-y-2">
                {projects.map((project) => (
                  <div
                    key={project.slug}
                    className="flex items-center justify-between p-3 bg-gray-700 rounded"
                  >
                    <div>
                      <div className="font-medium text-white">{project.name}</div>
                      <div className="text-sm text-gray-400 font-mono">{project.path}</div>
                    </div>
                    <div className="flex items-center space-x-2">
                      <Link
                        to={`/projects/${project.slug}`}
                        className="px-3 py-1 text-sm rounded bg-primary-600 text-white hover:bg-primary-500"
                      >
                        View
                      </Link>
                      <button
                        onClick={() => handleDeleteProject(project.slug)}
                        disabled={deletingSlug === project.slug}
                        className="px-3 py-1 text-sm rounded bg-red-800 text-red-200 hover:bg-red-700 disabled:opacity-50"
                      >
                        {deletingSlug === project.slug ? 'Removing...' : 'Remove'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Documentation */}
          <div className="card">
            <h2 className="text-lg font-semibold text-white mb-4">Documentation</h2>
            <div className="space-y-3 text-sm">
              <div>
                <h3 className="text-gray-300 font-medium">Configuration Files</h3>
                <p className="text-gray-400 mt-1">
                  Loop configurations are stored in <code className="bg-gray-700 px-1 rounded">.ralphx/loops/</code> as YAML files.
                </p>
              </div>
              <div>
                <h3 className="text-gray-300 font-medium">CLI Commands</h3>
                <ul className="text-gray-400 mt-1 space-y-1 font-mono text-xs">
                  <li>ralphx add &lt;path&gt; - Add a project</li>
                  <li>ralphx list - List projects</li>
                  <li>ralphx run &lt;slug&gt; &lt;loop&gt; - Run a loop</li>
                  <li>ralphx serve - Start the web server</li>
                  <li>ralphx mcp - Start MCP server for Claude Code</li>
                </ul>
              </div>
              <div>
                <h3 className="text-gray-300 font-medium">MCP Integration</h3>
                <p className="text-gray-400 mt-1">
                  Add RalphX to Claude Code:
                </p>
                <code className="block mt-1 px-3 py-2 bg-gray-700 rounded text-xs font-mono text-gray-300">
                  pip install ralphx
                </code>
                <code className="block mt-1 px-3 py-2 bg-gray-700 rounded text-xs font-mono text-gray-300">
                  claude mcp add ralphx -- ralphx mcp
                </code>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
