import { useState, useEffect, useCallback } from 'react'
import type { WorkflowStep } from '../../../api'
import { archiveWorkflowStep, listArchivedSteps, restoreWorkflowStep, deleteWorkflowStep } from '../../../api'
import StepList from './StepList'
import StepDetail from './StepDetail'
import ArchivedSteps from './ArchivedSteps'

interface StepsTabProps {
  projectSlug: string
  workflowId: string
  steps: WorkflowStep[]
  onStepsChange: (steps: WorkflowStep[]) => void
  onError: (error: string) => void
}

export default function StepsTab({
  projectSlug,
  workflowId,
  steps,
  onStepsChange,
  onError,
}: StepsTabProps) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(steps.length > 0 ? 0 : null)
  const [archivedSteps, setArchivedSteps] = useState<WorkflowStep[]>([])
  const [archivedLoading, setArchivedLoading] = useState(false)

  const selectedStep = selectedIndex !== null ? steps[selectedIndex] : null

  // Load archived steps when component mounts or workflowId changes
  const loadArchivedSteps = useCallback(async () => {
    if (!workflowId) return
    setArchivedLoading(true)
    try {
      const archived = await listArchivedSteps(projectSlug, workflowId)
      setArchivedSteps(archived)
    } catch (err) {
      // Silently fail - archived steps are optional
      console.error('Failed to load archived steps:', err)
    } finally {
      setArchivedLoading(false)
    }
  }, [projectSlug, workflowId])

  useEffect(() => {
    loadArchivedSteps()
  }, [loadArchivedSteps])

  const handleAddStep = () => {
    // Default to Implementation (consumer) type with its standard tools
    const newStep: WorkflowStep = {
      id: 0, // Will be assigned by server on save
      workflow_id: workflowId,
      step_number: steps.length + 1,
      name: 'New Step',
      step_type: 'autonomous',
      status: 'pending',
      config: {
        description: '',
        skippable: false,
        loopType: 'consumer',
        model: 'opus',
        timeout: 600,
        // Default tools for implementation/consumer steps
        allowedTools: ['Read', 'Write', 'Edit', 'Bash', 'Glob', 'Grep'],
      },
    }
    onStepsChange([...steps, newStep])
    setSelectedIndex(steps.length) // Select the new step
  }

  const handleCloneStep = (index: number) => {
    const sourceStep = steps[index]
    const clonedStep: WorkflowStep = {
      id: 0, // Will be assigned by server on save
      workflow_id: workflowId,
      step_number: steps.length + 1,
      name: `${sourceStep.name} (Copy)`,
      step_type: sourceStep.step_type,
      status: 'pending',
      config: {
        ...sourceStep.config,
      },
      // Don't copy progress data - start fresh
      iterations_completed: 0,
      items_generated: 0,
    }
    onStepsChange([...steps, clonedStep])
    setSelectedIndex(steps.length) // Select the cloned step
  }

  const handleArchiveStep = async (index: number) => {
    const step = steps[index]

    // If step has no ID (unsaved), just remove it from the list
    if (!step.id) {
      const newSteps = steps.filter((_, i) => i !== index)
      onStepsChange(newSteps)
      if (selectedIndex === index) {
        setSelectedIndex(newSteps.length > 0 ? Math.max(0, index - 1) : null)
      } else if (selectedIndex !== null && selectedIndex > index) {
        setSelectedIndex(selectedIndex - 1)
      }
      return
    }

    // Archive via API
    try {
      await archiveWorkflowStep(projectSlug, workflowId, step.id)

      // Remove from active steps
      const newSteps = steps.filter((_, i) => i !== index)
      onStepsChange(newSteps)

      // Add to archived steps
      setArchivedSteps(prev => [...prev, { ...step, archived_at: new Date().toISOString() }])

      // Adjust selection
      if (selectedIndex === index) {
        setSelectedIndex(newSteps.length > 0 ? Math.max(0, index - 1) : null)
      } else if (selectedIndex !== null && selectedIndex > index) {
        setSelectedIndex(selectedIndex - 1)
      }
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to archive step')
    }
  }

  const handleRestoreStep = async (archivedStep: WorkflowStep) => {
    try {
      const restored = await restoreWorkflowStep(projectSlug, workflowId, archivedStep.id)

      // Remove from archived
      setArchivedSteps(prev => prev.filter(s => s.id !== archivedStep.id))

      // Add back to active steps at original position
      const newSteps = [...steps]
      // Insert at the correct position based on step_number
      const insertIndex = newSteps.findIndex(s => s.step_number > restored.step_number)
      if (insertIndex === -1) {
        newSteps.push(restored)
      } else {
        newSteps.splice(insertIndex, 0, restored)
      }
      onStepsChange(newSteps)
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to restore step')
    }
  }

  const handlePermanentlyDelete = async (archivedStep: WorkflowStep) => {
    try {
      await deleteWorkflowStep(projectSlug, workflowId, archivedStep.id)
      setArchivedSteps(prev => prev.filter(s => s.id !== archivedStep.id))
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Failed to delete step')
    }
  }

  const handleMoveStep = (index: number, direction: 'up' | 'down') => {
    const newIndex = direction === 'up' ? index - 1 : index + 1
    if (newIndex < 0 || newIndex >= steps.length) return

    const newSteps = [...steps]
    const [moved] = newSteps.splice(index, 1)
    newSteps.splice(newIndex, 0, moved)
    onStepsChange(newSteps)

    // Update selection to follow the moved step
    if (selectedIndex === index) {
      setSelectedIndex(newIndex)
    } else if (selectedIndex === newIndex) {
      setSelectedIndex(index)
    }
  }

  const handleUpdateStep = (updatedStep: WorkflowStep) => {
    if (selectedIndex === null) return
    const newSteps = [...steps]
    newSteps[selectedIndex] = updatedStep
    onStepsChange(newSteps)
  }

  return (
    <div className="flex gap-6 h-[calc(100vh-220px)]">
      {/* Left Panel - Step List + Archived Steps */}
      <div className="w-64 flex-shrink-0 flex flex-col">
        <div className="flex-1 overflow-y-auto">
          <StepList
            steps={steps}
            selectedIndex={selectedIndex}
            onSelect={setSelectedIndex}
            onAdd={handleAddStep}
            onMove={handleMoveStep}
          />
        </div>

        {/* Archived Steps Section */}
        <ArchivedSteps
          archivedSteps={archivedSteps}
          loading={archivedLoading}
          onRestore={handleRestoreStep}
          onPermanentlyDelete={handlePermanentlyDelete}
        />
      </div>

      {/* Right Panel - Step Detail */}
      <div className="flex-1 min-w-0">
        {selectedStep ? (
          <StepDetail
            projectSlug={projectSlug}
            workflowId={workflowId}
            step={selectedStep}
            onChange={handleUpdateStep}
            onClone={() => handleCloneStep(selectedIndex!)}
            onArchive={() => handleArchiveStep(selectedIndex!)}
            onError={onError}
          />
        ) : (
          <div className="h-full flex items-center justify-center card">
            <div className="text-center">
              <svg className="w-16 h-16 mx-auto text-gray-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <h3 className="text-lg font-medium text-gray-300 mb-2">No Steps Yet</h3>
              <p className="text-gray-500 mb-4">Add your first step to define your workflow.</p>
              <button
                onClick={handleAddStep}
                className="px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-500"
              >
                Add First Step
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
