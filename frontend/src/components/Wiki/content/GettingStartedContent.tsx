import { WikiSection, CopyablePrompt, StepGuide, ConceptCard } from '../'

export default function GettingStartedContent() {
  return (
    <div className="space-y-8">
      {/* What is Claude Code? */}
      <WikiSection
        id="claude-code"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        }
        title="What is Claude Code?"
        description="Understanding the tool that powers your RalphX workflows"
      >
        <div className="space-y-4">
          <p className="text-gray-300">
            <strong className="text-white">Claude Code</strong> is a command-line assistant that can read and write files,
            run commands, and help you build software. It's like having an expert developer available in your terminal.
          </p>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
            <h4 className="text-sm font-medium text-white mb-3">How to install</h4>
            <div className="space-y-3">
              <div>
                <p className="text-xs text-gray-400 mb-1">macOS / Linux / WSL:</p>
                <div className="bg-gray-900 rounded p-3 font-mono text-sm text-cyan-400">
                  curl -fsSL https://claude.ai/install.sh | bash
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-400 mb-1">Windows (PowerShell):</p>
                <div className="bg-gray-900 rounded p-3 font-mono text-sm text-cyan-400">
                  irm https://claude.ai/install.ps1 | iex
                </div>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-3">
              Visit{' '}
              <a
                href="https://code.claude.com/docs/en/setup"
                target="_blank"
                rel="noopener noreferrer"
                className="text-cyan-400 hover:underline"
              >
                Claude Code documentation
              </a>
              {' '}for more options including Homebrew and WinGet.
            </p>
          </div>

          <StepGuide
            steps={[
              {
                title: 'Open your terminal',
                description: 'On Mac: Press Cmd+Space, type "Terminal", press Enter. On Windows: Press Win+R, type "cmd", press Enter.',
              },
              {
                title: 'Type "claude" and press Enter',
                description: 'This starts Claude Code. You\'ll see a prompt where you can type or paste commands.',
              },
              {
                title: 'Copy a prompt from this wiki',
                description: 'Click the "Copy" button on any prompt block below.',
              },
              {
                title: 'Paste into Claude Code',
                description: 'Press Ctrl+V (or Cmd+V on Mac) to paste, then press Enter. Claude will handle the rest!',
              },
            ]}
          />
        </div>
      </WikiSection>

      {/* Key Concepts */}
      <WikiSection
        id="concepts"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
          </svg>
        }
        title="Key Concepts"
        description="The building blocks of RalphX"
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <ConceptCard
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
            }
            title="Project"
            description="A folder on your computer that contains code you want to work on. Each project can have multiple workflows."
            color="cyan"
          />
          <ConceptCard
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            }
            title="Workflow"
            description="A sequence of steps to accomplish something. Workflows can plan features, implement code, research topics, or generate docs."
            color="emerald"
          />
          <ConceptCard
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            }
            title="Step"
            description="One stage in a workflow. For example: 'Generate user stories', then 'Review and prioritize', then 'Implement features'."
            color="amber"
          />
          <ConceptCard
            icon={
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            }
            title="Work Item"
            description="A specific task to complete. Could be a user story, bug fix, or any unit of work that Claude will tackle."
            color="violet"
          />
        </div>
      </WikiSection>

      {/* Your First Workflow */}
      <WikiSection
        id="first-workflow"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        }
        title="Your First Workflow"
        description="Create a workflow in seconds with this prompt"
      >
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Copy this prompt and paste it into Claude Code. It will ask you a few questions, then set everything up automatically.
          </p>
          <CopyablePrompt
            title="Create your first workflow"
            description="This prompt guides you through creating a project and workflow by asking what you want to build and what type of workflow you need."
            prompt={`Help me set up my first RalphX workflow. Ask me:
1. What project folder should we use?
2. What do I want to build or accomplish?
3. Should this be a planning workflow (generate tasks) or implementation workflow (build features)?

Then create the project and workflow for me.`}
          />
        </div>
      </WikiSection>
    </div>
  )
}
