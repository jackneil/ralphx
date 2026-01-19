import { useEffect, useState } from 'react'
import { Link, useParams, useLocation } from 'react-router-dom'
import { useDashboardStore } from '../stores/dashboard'
import { listWorkflows, Workflow } from '../api'

export default function Sidebar() {
  const { slug, workflowId } = useParams()
  const location = useLocation()
  const {
    projects,
    projectsLoading,
    projectsError,
    loadProjects,
  } = useDashboardStore()

  const [expandedProject, setExpandedProject] = useState<string | null>(null)
  const [projectWorkflows, setProjectWorkflows] = useState<Record<string, Workflow[]>>({})

  useEffect(() => {
    loadProjects()
  }, [loadProjects])

  // Auto-expand current project
  useEffect(() => {
    if (slug) {
      setExpandedProject(slug)
    }
  }, [slug])

  // Load workflows for expanded project
  useEffect(() => {
    if (!expandedProject || projectWorkflows[expandedProject]) return

    listWorkflows(expandedProject)
      .then(workflows => {
        setProjectWorkflows(prev => ({ ...prev, [expandedProject]: workflows }))
      })
      .catch(() => {
        setProjectWorkflows(prev => ({ ...prev, [expandedProject]: [] }))
      })
  }, [expandedProject, projectWorkflows])

  const isSettingsPage = location.pathname.endsWith('/settings')

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
          {projects.map((project) => {
            const isExpanded = expandedProject === project.slug
            const isActive = slug === project.slug
            const workflows = projectWorkflows[project.slug] || []
            const activeWorkflows = workflows.filter(w => w.status === 'active' || w.status === 'draft' || w.status === 'paused')

            return (
              <li key={project.slug}>
                <div className="flex items-center">
                  {/* Expand/collapse button */}
                  <button
                    onClick={() => setExpandedProject(isExpanded ? null : project.slug)}
                    className="p-1 text-gray-500 hover:text-white"
                    aria-label={isExpanded ? 'Collapse' : 'Expand'}
                  >
                    <svg
                      className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>

                  {/* Project link */}
                  <Link
                    to={`/projects/${project.slug}`}
                    className={`flex-1 block px-2 py-2 rounded-md text-sm transition-colors ${
                      isActive && !workflowId && !isSettingsPage
                        ? 'bg-primary-600 text-white'
                        : 'text-gray-300 hover:bg-gray-700 hover:text-white'
                    }`}
                  >
                    <div className="font-medium">{project.name}</div>
                  </Link>
                </div>

                {/* Expanded content - workflows */}
                {isExpanded && (
                  <div className="ml-6 mt-1 space-y-1">
                    {activeWorkflows.length > 0 ? (
                      activeWorkflows.slice(0, 5).map(workflow => {
                        const currentStep = workflow.steps.find(s => s.step_number === workflow.current_step)
                        return (
                          <Link
                            key={workflow.id}
                            to={`/projects/${project.slug}/workflows/${workflow.id}`}
                            className={`block px-2 py-1.5 rounded text-xs transition-colors ${
                              workflowId === workflow.id
                                ? 'bg-gray-700 text-white'
                                : 'text-gray-400 hover:bg-gray-700 hover:text-white'
                            }`}
                          >
                            <div className="flex items-center space-x-2">
                              <span className={`w-1.5 h-1.5 rounded-full ${
                                workflow.status === 'active' ? 'bg-green-400 animate-pulse' : 'bg-gray-500'
                              }`} />
                              <span className="truncate">{workflow.name}</span>
                            </div>
                            {currentStep && workflow.status === 'active' && (
                              <div className="ml-4 mt-0.5 text-[10px] text-gray-500 truncate">
                                Step {workflow.current_step}: {currentStep.name}
                              </div>
                            )}
                          </Link>
                        )
                      })
                    ) : (
                      <div className="px-2 py-1 text-xs text-gray-500">
                        No active workflows
                      </div>
                    )}

                    {activeWorkflows.length > 5 && (
                      <Link
                        to={`/projects/${project.slug}`}
                        className="block px-2 py-1 text-xs text-gray-500 hover:text-gray-400"
                      >
                        +{activeWorkflows.length - 5} more
                      </Link>
                    )}

                    {/* Project Settings link */}
                    <Link
                      to={`/projects/${project.slug}/settings`}
                      className={`block px-2 py-1.5 rounded text-xs transition-colors ${
                        isSettingsPage && slug === project.slug
                          ? 'bg-gray-700 text-white'
                          : 'text-gray-500 hover:bg-gray-700 hover:text-gray-300'
                      }`}
                    >
                      <div className="flex items-center space-x-2">
                        <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                        </svg>
                        <span>Settings</span>
                      </div>
                    </Link>
                  </div>
                )}
              </li>
            )
          })}
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
          to="/wiki"
          className="flex items-center space-x-2 text-sm text-gray-400 hover:text-white transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
          </svg>
          <span>Wiki</span>
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
