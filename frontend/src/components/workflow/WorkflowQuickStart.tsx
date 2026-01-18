import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { createWorkflow, createWorkflowResource } from '../../api'

interface WorkflowQuickStartProps {
  projectSlug: string
  onWorkflowCreated?: () => void
}

interface QuickStartCard {
  templateId: string
  title: string
  description: string
  icon: React.ReactNode
  stepCount: string
  recommended?: boolean
  requiresInput?: 'design_doc' | 'stories'
}

const QUICK_START_CARDS: QuickStartCard[] = [
  {
    templateId: 'build-product',
    title: 'Build from Scratch',
    description: 'Start with an idea. Claude helps you plan, design, and build step by step.',
    stepCount: '3 steps',
    recommended: true,
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
  },
  {
    templateId: 'from-design-doc',
    title: 'I Have a Design Doc',
    description: 'Upload your design document. Claude generates stories and implements them.',
    stepCount: '2 steps',
    requiresInput: 'design_doc',
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    templateId: 'from-stories',
    title: 'I Have User Stories',
    description: 'Import your existing stories. Claude implements them one by one.',
    stepCount: '1 step',
    requiresInput: 'stories',
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
      </svg>
    ),
  },
  {
    templateId: 'planning-only',
    title: 'Just Plan',
    description: 'Create a design document through interactive planning with Claude.',
    stepCount: '1 step',
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
      </svg>
    ),
  },
]

type WizardStep = 'name' | 'input' | 'creating'

export default function WorkflowQuickStart({ projectSlug, onWorkflowCreated }: WorkflowQuickStartProps) {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [creating, setCreating] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showModal, setShowModal] = useState<QuickStartCard | null>(null)
  const [wizardStep, setWizardStep] = useState<WizardStep>('name')

  // Step 1: Name
  const [workflowName, setWorkflowName] = useState('')
  const [isNewProject, setIsNewProject] = useState(false)

  // Step 2: Input content
  const [inputContent, setInputContent] = useState('')
  const [inputFileName, setInputFileName] = useState<string | null>(null)

  const handleCardClick = (card: QuickStartCard) => {
    setShowModal(card)
    setWizardStep('name')
    setWorkflowName('')
    setIsNewProject(false)
    setInputContent('')
    setInputFileName(null)
    setError(null)
  }

  const handleCloseModal = () => {
    setShowModal(null)
    setWizardStep('name')
    setError(null)
  }

  const handleNextStep = () => {
    if (!workflowName.trim()) return

    // If this template requires input, go to input step
    if (showModal?.requiresInput) {
      setWizardStep('input')
    } else {
      // Otherwise create workflow directly
      handleCreateWorkflow()
    }
  }

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (event) => {
      const text = event.target?.result as string
      setInputContent(text)
      setInputFileName(file.name)
    }
    reader.readAsText(file)
  }

  const handleCreateWorkflow = async () => {
    if (!showModal || !workflowName.trim()) return

    // For templates requiring input, check if content is provided
    if (showModal.requiresInput && !inputContent.trim()) {
      setError(`Please provide your ${showModal.requiresInput === 'design_doc' ? 'design document' : 'user stories'}`)
      return
    }

    setCreating(showModal.templateId)
    setWizardStep('creating')
    setError(null)

    let createdWorkflow: { id: string } | null = null

    try {
      // Create the workflow
      createdWorkflow = await createWorkflow(projectSlug, {
        template_id: showModal.templateId,
        name: workflowName.trim(),
        config: isNewProject ? { architecture_first: true } : undefined,
      })

      // If there's input content, save it as a workflow resource
      if (inputContent.trim() && showModal.requiresInput) {
        const resourceType = showModal.requiresInput === 'design_doc' ? 'design_doc' : 'input_file'
        const resourceName = showModal.requiresInput === 'design_doc'
          ? 'Design Document'
          : 'Imported Stories'

        try {
          await createWorkflowResource(projectSlug, createdWorkflow.id, {
            resource_type: resourceType,
            name: resourceName,
            content: inputContent.trim(),
            source: 'upload',
          })
        } catch (resourceErr) {
          // Resource creation failed but workflow exists - still navigate to workflow
          // User can manually add resource later
          console.error('Failed to upload resource:', resourceErr)
          setShowModal(null)
          onWorkflowCreated?.()
          navigate(`/projects/${projectSlug}/workflows/${createdWorkflow.id}`)
          return
        }
      }

      setShowModal(null)
      onWorkflowCreated?.()
      navigate(`/projects/${projectSlug}/workflows/${createdWorkflow.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create workflow')
      // Only go back to input step if workflow creation itself failed
      if (!createdWorkflow) {
        setWizardStep(showModal.requiresInput ? 'input' : 'name')
      }
    } finally {
      setCreating(null)
    }
  }

  const getTotalSteps = () => {
    if (!showModal) return 1
    return showModal.requiresInput ? 2 : 1
  }

  const getCurrentStep = () => {
    if (wizardStep === 'name') return 1
    return 2
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-white mb-2">What would you like to do?</h2>
        <p className="text-gray-400">Choose how you want to start your project</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {QUICK_START_CARDS.map((card) => (
          <button
            key={card.templateId}
            onClick={() => handleCardClick(card)}
            disabled={creating !== null}
            className={`p-6 rounded-lg border text-left transition-all group ${
              card.recommended
                ? 'bg-primary-900/20 border-primary-600 hover:border-primary-500'
                : 'bg-gray-800 border-gray-700 hover:border-gray-600'
            } ${creating !== null ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <div className="flex items-start space-x-4">
              <div className={`w-12 h-12 rounded-lg flex items-center justify-center flex-shrink-0 ${
                card.recommended ? 'bg-primary-600' : 'bg-gray-700'
              }`}>
                <span className={card.recommended ? 'text-white' : 'text-gray-300'}>
                  {card.icon}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center space-x-2">
                  <h3 className={`text-lg font-semibold transition-colors ${
                    card.recommended
                      ? 'text-white group-hover:text-primary-300'
                      : 'text-white group-hover:text-gray-200'
                  }`}>
                    {card.title}
                  </h3>
                  {card.recommended && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-primary-600 text-primary-100">
                      Recommended
                    </span>
                  )}
                </div>
                <p className="text-sm text-gray-400 mt-1">{card.description}</p>
                <p className="text-xs text-gray-500 mt-2">{card.stepCount}</p>
              </div>
              <svg className="w-5 h-5 text-gray-500 group-hover:text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </button>
        ))}
      </div>

      {/* Multi-step Wizard Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg border border-gray-700 p-6 max-w-lg w-full mx-4">
            {/* Header with step indicator */}
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-white">
                {wizardStep === 'name' ? `Create ${showModal.title} Workflow` :
                 wizardStep === 'input' && showModal.requiresInput === 'design_doc' ? 'Upload Design Document' :
                 wizardStep === 'input' && showModal.requiresInput === 'stories' ? 'Import User Stories' :
                 'Creating Workflow...'}
              </h3>
              {getTotalSteps() > 1 && wizardStep !== 'creating' && (
                <span className="text-sm text-gray-400">
                  Step {getCurrentStep()} of {getTotalSteps()}
                </span>
              )}
            </div>

            {/* Step 1: Name */}
            {wizardStep === 'name' && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="workflow-name" className="block text-sm font-medium text-gray-300 mb-1">
                    Workflow Name
                  </label>
                  <input
                    id="workflow-name"
                    type="text"
                    value={workflowName}
                    onChange={(e) => setWorkflowName(e.target.value)}
                    placeholder="e.g., My Awesome App"
                    className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && workflowName.trim()) {
                        handleNextStep()
                      }
                    }}
                  />
                </div>

                {showModal.templateId === 'build-product' && (
                  <div className="flex items-start space-x-3 p-3 bg-gray-700/50 rounded">
                    <input
                      id="new-project"
                      type="checkbox"
                      checked={isNewProject}
                      onChange={(e) => setIsNewProject(e.target.checked)}
                      className="mt-1 rounded bg-gray-600 border-gray-500"
                    />
                    <label htmlFor="new-project" className="text-sm text-gray-300">
                      <span className="font-medium">This is a new project</span>
                      <p className="text-gray-400 mt-0.5">
                        Build foundation architecture first by grouping initial stories together
                      </p>
                    </label>
                  </div>
                )}

                {error && (
                  <div className="p-3 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
                    {error}
                  </div>
                )}

                <div className="flex justify-end space-x-3 pt-2">
                  <button
                    onClick={handleCloseModal}
                    className="px-4 py-2 text-sm text-gray-400 hover:text-white"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleNextStep}
                    disabled={!workflowName.trim()}
                    className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {showModal.requiresInput ? 'Next' : 'Create Workflow'}
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: Input (Design Doc or Stories) */}
            {wizardStep === 'input' && showModal.requiresInput && (
              <div className="space-y-4">
                <p className="text-sm text-gray-400">
                  {showModal.requiresInput === 'design_doc'
                    ? 'Claude will use your design document to generate implementation stories.'
                    : 'Paste your user stories below. Claude will implement them one by one.'}
                </p>

                {/* File upload area */}
                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed border-gray-600 rounded-lg p-6 text-center hover:border-gray-500 cursor-pointer transition-colors"
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".md,.txt,.json,.jsonl"
                    onChange={handleFileUpload}
                    className="hidden"
                  />
                  <svg className="w-8 h-8 mx-auto text-gray-500 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                  </svg>
                  {inputFileName ? (
                    <p className="text-sm text-primary-400">{inputFileName}</p>
                  ) : (
                    <p className="text-sm text-gray-400">
                      Click to upload a file (.md, .txt, .json, .jsonl)
                    </p>
                  )}
                </div>

                <div className="text-center text-sm text-gray-500">or paste below</div>

                <textarea
                  value={inputContent}
                  onChange={(e) => {
                    setInputContent(e.target.value)
                    setInputFileName(null)
                  }}
                  placeholder={showModal.requiresInput === 'design_doc'
                    ? '# My Product\n\n## Overview\n...'
                    : 'As a user, I want to...\n\nAs an admin, I want to...'}
                  rows={8}
                  className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded text-white placeholder-gray-400 focus:outline-none focus:border-primary-500 font-mono text-sm resize-none"
                />

                {showModal.requiresInput === 'stories' && (
                  <p className="text-xs text-gray-500">
                    Supports: Plain text (one story per line), Markdown lists, or JSONL format
                  </p>
                )}

                {error && (
                  <div className="p-3 bg-red-900/30 border border-red-800 rounded text-sm text-red-400">
                    {error}
                  </div>
                )}

                <div className="flex justify-between pt-2">
                  <button
                    onClick={() => setWizardStep('name')}
                    className="px-4 py-2 text-sm text-gray-400 hover:text-white"
                  >
                    Back
                  </button>
                  <div className="flex space-x-3">
                    <button
                      onClick={handleCloseModal}
                      className="px-4 py-2 text-sm text-gray-400 hover:text-white"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleCreateWorkflow}
                      disabled={!inputContent.trim() || creating !== null}
                      className="px-4 py-2 text-sm bg-primary-600 text-white rounded hover:bg-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {creating ? 'Creating...' : 'Start Workflow'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Creating step */}
            {wizardStep === 'creating' && (
              <div className="py-8 text-center">
                <div className="w-12 h-12 border-4 border-primary-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
                <p className="text-gray-300">Creating your workflow...</p>
                {showModal.requiresInput && inputContent && (
                  <p className="text-sm text-gray-500 mt-2">Uploading resources...</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
