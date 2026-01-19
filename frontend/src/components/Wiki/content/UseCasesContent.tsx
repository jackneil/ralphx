import { WikiSection, CopyablePrompt } from '../'

export default function UseCasesContent() {
  return (
    <div className="space-y-8">
      {/* Planning Workflow */}
      <WikiSection
        id="planning"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
        }
        title="Planning Workflow"
        description="Generate user stories and break down complex projects"
      >
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Use a planning workflow when you have an idea but need to break it down into actionable tasks.
            Claude will analyze your requirements and generate a prioritized list of user stories.
          </p>
          <CopyablePrompt
            title="Create a planning workflow"
            description="Sets up a workflow that will generate user stories and break down your project into manageable tasks."
            prompt={`Help me create a planning workflow in RalphX. Ask me what I want
to build, then set up a workflow that will generate user stories
and break down the work into manageable tasks.`}
          />
          <div className="text-xs text-gray-500">
            <strong>Best for:</strong> New features, product ideas, project kickoffs
          </div>
        </div>
      </WikiSection>

      {/* Implementation Workflow */}
      <WikiSection
        id="implementation"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
          </svg>
        }
        title="Implementation Workflow"
        description="Write code and build features automatically"
      >
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Use an implementation workflow when you have tasks ready and want Claude to build them.
            It will work through each item, writing code and committing changes.
          </p>
          <CopyablePrompt
            title="Create an implementation workflow"
            description="Sets up a workflow that will implement your tasks one by one, writing code and committing as it goes."
            prompt={`Help me create an implementation workflow in RalphX. I have user
stories/tasks ready. Set up a workflow that will implement them
one by one, committing code as it goes.`}
          />
          <div className="text-xs text-gray-500">
            <strong>Best for:</strong> Building features, fixing bugs, code improvements
          </div>
        </div>
      </WikiSection>

      {/* Research Workflow */}
      <WikiSection
        id="research"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        }
        title="Research Workflow"
        description="Investigate topics and gather information"
      >
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Use a research workflow when you need to explore a topic, compare options,
            or gather information before making decisions.
          </p>
          <CopyablePrompt
            title="Create a research workflow"
            description="Sets up a workflow that will investigate a topic and summarize findings."
            prompt={`Help me create a research workflow in RalphX. Ask me what topic
I want to research, then set up a workflow that will investigate
it and summarize findings.`}
          />
          <div className="text-xs text-gray-500">
            <strong>Best for:</strong> Technology comparisons, library selection, architecture decisions
          </div>
        </div>
      </WikiSection>

      {/* Documentation Workflow */}
      <WikiSection
        id="documentation"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        }
        title="Documentation Workflow"
        description="Generate docs for your code automatically"
      >
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Use a documentation workflow to generate READMEs, API docs, or any other
            documentation your project needs.
          </p>
          <CopyablePrompt
            title="Create a documentation workflow"
            description="Sets up a workflow to analyze your code and generate documentation."
            prompt={`Help me create a documentation workflow in RalphX. Ask me what
code/project needs documentation, then set up a workflow to
generate docs automatically.`}
          />
          <div className="text-xs text-gray-500">
            <strong>Best for:</strong> README files, API documentation, code comments
          </div>
        </div>
      </WikiSection>

      {/* Custom Workflow */}
      <WikiSection
        id="custom"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
          </svg>
        }
        title="Custom Workflow"
        description="Design a workflow for your specific needs"
      >
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Not sure what type of workflow you need? Describe what you want to accomplish
            and Claude will help design the right workflow for you.
          </p>
          <CopyablePrompt
            title="Create a custom workflow"
            description="Describes your goal and lets Claude design the appropriate workflow."
            prompt={`Help me create a custom RalphX workflow. Here's what I want to
accomplish: [describe your goal here]

Help me figure out what steps and work items would make sense,
then create the workflow.`}
            variant="secondary"
          />
        </div>
      </WikiSection>
    </div>
  )
}
