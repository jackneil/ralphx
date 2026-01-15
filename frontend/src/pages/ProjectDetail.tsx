import { useEffect, useState, useRef, useCallback } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { useDashboardStore, type Loop } from '../stores/dashboard'
import { getProject, listLoops, getLoopStatus, createLoop } from '../api'
import LoopCard from '../components/LoopCard'
import LoopBuilder from '../components/LoopBuilder/LoopBuilder'
import SimpleLoopWizard from '../components/SimpleLoopWizard'
import { EmptyState, EMPTY_STATE_ICONS } from '../components/Help'
import ResourceManager from '../components/ResourceManager/ResourceManager'
import AuthPanel from '../components/AuthPanel'

export default function ProjectDetail() {
  const { slug } = useParams<{ slug: string }>()
  const navigate = useNavigate()
  const {
    selectedProject,
    loops,
    loopsLoading,
    setSelectedProject,
    setLoops,
    setLoopsLoading,
    updateLoop,
  } = useDashboardStore()

  const [error, setError] = useState<string | null>(null)
  const [loopsError, setLoopsError] = useState<string | null>(null)
  const [showCreateLoop, setShowCreateLoop] = useState(false)
  const [showAdvancedBuilder, setShowAdvancedBuilder] = useState(false)
  const [showResources, setShowResources] = useState(true)

  // Use ref to track loops for polling without causing re-renders
  const loopsRef = useRef<Loop[]>([])
  loopsRef.current = loops

  // Load loops function - reusable for initial load and after create
  const loadLoopsData = useCallback(async () => {
    if (!slug) return
    setLoopsLoading(true)
    setLoopsError(null)
    try {
      const loopList = await listLoops(slug)
      const loopsWithStatus: Loop[] = await Promise.all(
        loopList.map(async (loop) => {
          try {
            const status = await getLoopStatus(slug, loop.name)
            return {
              ...loop,
              is_running: status.is_running,
              current_iteration: status.current_iteration,
              current_mode: status.current_mode,
            }
          } catch {
            return { ...loop, is_running: false }
          }
        })
      )
      setLoops(loopsWithStatus)
    } catch (err) {
      console.error('Failed to load loops:', err)
      setLoopsError(err instanceof Error ? err.message : 'Failed to load loops')
      setLoops([])
    } finally {
      setLoopsLoading(false)
    }
  }, [slug, setLoops, setLoopsLoading])

  // Handle creating a new loop
  const handleCreateLoop = useCallback(async (yamlContent: string) => {
    if (!slug) return

    // Extract the loop name from the YAML content
    const nameMatch = yamlContent.match(/^name:\s*(.+)$/m)
    if (!nameMatch) {
      throw new Error('Loop name not found in configuration')
    }
    const loopName = nameMatch[1].trim().replace(/["']/g, '')

    await createLoop(slug, loopName, yamlContent)
    setShowCreateLoop(false)
    await loadLoopsData()
  }, [slug, loadLoopsData])

  useEffect(() => {
    if (!slug) return

    // Clear stale data immediately when slug changes to prevent showing old project
    setSelectedProject(null)
    setLoops([])
    setLoopsError(null)

    async function loadProject() {
      setError(null)
      try {
        const project = await getProject(slug!)
        setSelectedProject(project)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load project')
      }
    }

    loadProject()
    loadLoopsData()

    // Poll loop status using ref to avoid infinite re-renders
    // The ref always has current loops without triggering effect re-runs
    const interval = setInterval(async () => {
      const currentLoops = loopsRef.current
      for (const loop of currentLoops) {
        try {
          const status = await getLoopStatus(slug!, loop.name)
          updateLoop(loop.name, {
            is_running: status.is_running,
            current_iteration: status.current_iteration,
            current_mode: status.current_mode,
          })
        } catch {
          // Ignore polling errors
        }
      }
    }, 5000)

    return () => clearInterval(interval)
  }, [slug, setSelectedProject, setLoops, setLoopsLoading, updateLoop])

  if (error) {
    return (
      <div className="p-6">
        <div className="card bg-red-900/20 border border-red-800">
          <h2 className="text-lg font-semibold text-red-400 mb-2">Error</h2>
          <p className="text-gray-300">{error}</p>
          <Link to="/" className="btn-secondary mt-4 inline-block">
            Back to Dashboard
          </Link>
        </div>
      </div>
    )
  }

  if (!selectedProject) {
    return (
      <div className="p-6">
        <div className="text-gray-400">Loading project...</div>
      </div>
    )
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center space-x-2 text-sm text-gray-400 mb-2">
          <Link to="/" className="hover:text-white">Dashboard</Link>
          <span>/</span>
          <span className="text-white">{selectedProject.name}</span>
        </div>
        <h1 className="text-3xl font-bold text-white mb-2">{selectedProject.name}</h1>
        <p className="text-gray-400">{selectedProject.path}</p>
      </div>

      {/* Navigation Links */}
      <div className="flex space-x-4 mb-6">
        <Link
          to={`/projects/${slug}/runs`}
          className="px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
        >
          View Run History
        </Link>
      </div>

      {/* Stats */}
      {selectedProject.stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <div className="card">
            <div className="text-2xl font-bold text-primary-400">
              {selectedProject.stats.total_items}
            </div>
            <div className="text-sm text-gray-400">Total Items</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-yellow-400">
              {selectedProject.stats.pending_items}
            </div>
            <div className="text-sm text-gray-400">Pending</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-green-400">
              {selectedProject.stats.completed_items}
            </div>
            <div className="text-sm text-gray-400">Completed</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-primary-400">
              {selectedProject.stats.loops}
            </div>
            <div className="text-sm text-gray-400">Loops</div>
          </div>
          <div className="card">
            <div className="text-2xl font-bold text-green-400">
              {selectedProject.stats.active_runs}
            </div>
            <div className="text-sm text-gray-400">Active Runs</div>
          </div>
        </div>
      )}

      {/* Loops */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Loops</h2>
          <button
            onClick={() => {
              setShowAdvancedBuilder(false)
              setShowCreateLoop(true)
            }}
            className="flex items-center space-x-2 px-4 py-2 bg-primary-600 text-white rounded hover:bg-primary-500 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>Create Loop</span>
          </button>
        </div>

        {loopsLoading ? (
          <div className="text-gray-400">Loading loops...</div>
        ) : loopsError ? (
          <div className="card bg-red-900/20 border border-red-800">
            <p className="text-red-400">{loopsError}</p>
            <p className="text-sm text-gray-400 mt-2">
              Unable to load loops. Check that the API is running.
            </p>
          </div>
        ) : loops.length === 0 ? (
          <div className="card">
            <EmptyState
              icon={EMPTY_STATE_ICONS.loop}
              title="No loops configured"
              description="Create your first loop to start automating your development workflow with AI."
              action={{
                label: 'Create Loop',
                onClick: () => {
                  setShowAdvancedBuilder(false)
                  setShowCreateLoop(true)
                },
              }}
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {loops.map((loop) => (
              <LoopCard
                key={loop.name}
                projectSlug={slug!}
                loop={loop}
              />
            ))}
          </div>
        )}
      </div>

      {/* Resources Section */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-white">Project Resources</h2>
          <button
            onClick={() => setShowResources(!showResources)}
            className="flex items-center space-x-2 px-4 py-2 bg-gray-700 text-gray-300 rounded hover:bg-gray-600 transition-colors"
          >
            <svg
              className={`w-5 h-5 transition-transform ${showResources ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
            <span>{showResources ? 'Hide' : 'Show'}</span>
          </button>
        </div>

        {showResources && (
          <div className="card">
            <ResourceManager projectSlug={slug!} />
          </div>
        )}

        {!showResources && (
          <p className="text-sm text-gray-400">
            Manage design docs, architecture, coding standards, and other resources that get injected into loop prompts.
          </p>
        )}
      </div>

      {/* Project Authentication Section */}
      {selectedProject && (
        <div className="mb-8">
          <h2 className="text-xl font-semibold text-white mb-4">Project Authentication</h2>
          <div className="card">
            <p className="text-gray-400 text-sm mb-4">
              Use a specific Claude account for this project, or use your global account from Settings.
            </p>
            <AuthPanel projectPath={selectedProject.path} />
          </div>
        </div>
      )}

      {/* Create Loop Modal - Simple Wizard by default */}
      {showCreateLoop && !showAdvancedBuilder && (
        <SimpleLoopWizard
          projectSlug={slug!}
          availableLoops={loops.map((l) => l.name)}
          onClose={() => setShowCreateLoop(false)}
          onCreated={async (loopName) => {
            setShowCreateLoop(false)
            await loadLoopsData()
            navigate(`/projects/${slug}/loops/${loopName}`)
          }}
          onAdvanced={() => {
            setShowAdvancedBuilder(true)
          }}
        />
      )}

      {/* Advanced Loop Builder */}
      {showCreateLoop && showAdvancedBuilder && (
        <LoopBuilder
          projectSlug={slug!}
          availableLoops={loops.map((l) => l.name)}
          onClose={() => {
            setShowCreateLoop(false)
            setShowAdvancedBuilder(false)
          }}
          onSave={handleCreateLoop}
        />
      )}
    </div>
  )
}
