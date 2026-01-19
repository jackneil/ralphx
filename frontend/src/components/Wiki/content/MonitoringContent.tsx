import { WikiSection, CopyablePrompt, QuickAnswer } from '../'

export default function MonitoringContent() {
  return (
    <div className="space-y-8">
      {/* Understanding the Dashboard */}
      <WikiSection
        id="dashboard"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z" />
          </svg>
        }
        title="Understanding the Dashboard"
        description="What the different parts of RalphX show you"
      >
        <div className="space-y-4">
          <div className="grid gap-4">
            <div className="bg-gray-800/30 rounded-lg p-4 border border-gray-700/50">
              <div className="flex items-center space-x-2 mb-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-sm font-medium text-white">Active Workflow</span>
              </div>
              <p className="text-xs text-gray-400">
                A green pulsing dot means the workflow is currently running. Claude is actively working on tasks.
              </p>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 border border-gray-700/50">
              <div className="flex items-center space-x-2 mb-2">
                <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
                <span className="text-sm font-medium text-white">Paused Workflow</span>
              </div>
              <p className="text-xs text-gray-400">
                An amber dot means the workflow is paused. It's waiting for you to resume or make changes.
              </p>
            </div>
            <div className="bg-gray-800/30 rounded-lg p-4 border border-gray-700/50">
              <div className="flex items-center space-x-2 mb-2">
                <span className="w-2.5 h-2.5 rounded-full bg-gray-500" />
                <span className="text-sm font-medium text-white">Completed/Draft</span>
              </div>
              <p className="text-xs text-gray-400">
                A gray dot means the workflow is either complete or still in draft mode (not yet started).
              </p>
            </div>
          </div>
        </div>
      </WikiSection>

      {/* Workflow Management */}
      <WikiSection
        id="management"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        }
        title="Managing Workflows"
        description="Control your running workflows"
      >
        <div className="space-y-4">
          <CopyablePrompt
            title="Stop a workflow"
            description="Gracefully stops the currently running workflow, finishing any in-progress task."
            prompt={`Stop my currently running RalphX workflow gracefully.`}
          />

          <CopyablePrompt
            title="Pause and review"
            description="Pauses the workflow so you can review what's been done before continuing."
            prompt={`Pause the workflow so I can review progress, then resume when ready.`}
          />

          <CopyablePrompt
            title="Check progress"
            description="Shows what the workflow has accomplished so far."
            prompt={`Show me what my workflow has accomplished so far - list the
work items and their status.`}
          />

          <CopyablePrompt
            title="Delete a workflow"
            description="Removes a workflow (will ask for confirmation first)."
            prompt={`Delete the workflow named [X] - ask me to confirm first.`}
            variant="secondary"
          />
        </div>
      </WikiSection>

      {/* Troubleshooting */}
      <WikiSection
        id="troubleshooting"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
        title="Troubleshooting"
        description="Fix common issues"
      >
        <div className="space-y-4">
          <CopyablePrompt
            title="Diagnose a stuck workflow"
            description="Checks logs and status to figure out why a workflow isn't progressing."
            prompt={`My RalphX workflow seems stuck. Help me diagnose what's wrong
by checking the logs and status.`}
          />

          <CopyablePrompt
            title="Handle a failed work item"
            description="Investigates why a task failed and helps you retry or skip it."
            prompt={`A work item failed. Help me understand why and either retry it
or skip it.`}
          />

          <CopyablePrompt
            title="RalphX won't start"
            description="Checks dependencies and configuration to fix startup issues."
            prompt={`RalphX isn't starting properly. Help me troubleshoot the issue
by checking if all dependencies are installed and the server can start.`}
          />
        </div>
      </WikiSection>

      {/* FAQ */}
      <WikiSection
        id="faq"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
        title="Frequently Asked Questions"
      >
        <div className="space-y-3">
          <QuickAnswer question="Can I run multiple workflows at once?">
            Yes! Each workflow runs independently. You can have a planning workflow for one feature
            while an implementation workflow builds another.
          </QuickAnswer>

          <QuickAnswer question="What happens if I close my browser?">
            RalphX continues running in the background (as long as the terminal running ./dev.sh stays open).
            When you come back, you'll see the current state of all workflows.
          </QuickAnswer>

          <QuickAnswer question="Can I edit work items while a workflow is running?">
            Yes, but be careful - editing items that are currently being processed might cause issues.
            It's best to pause the workflow first, make your changes, then resume.
          </QuickAnswer>

          <QuickAnswer question="How do I add more tasks to a running workflow?">
            You can add work items through the UI by clicking into a workflow and using the "Add Item" button,
            or ask Claude to add items using a prompt.
          </QuickAnswer>

          <QuickAnswer question="What if Claude makes a mistake?">
            You can always revert changes using git. RalphX commits changes incrementally, so you can
            use git log to see what was changed and git revert to undo specific commits.
          </QuickAnswer>
        </div>
      </WikiSection>
    </div>
  )
}
