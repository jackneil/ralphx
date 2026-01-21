import { WikiSection, CopyablePrompt, StepGuide, ConceptCard } from '../'

export default function BackupImportContent() {
  return (
    <div className="space-y-8">
      {/* Overview */}
      <WikiSection
        id="overview"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        }
        title="Backup & Import Overview"
        description="Save your workflows and share them with others"
      >
        <div className="space-y-4">
          <p className="text-gray-300">
            RalphX lets you <strong className="text-white">export workflows</strong> as portable backup files
            and <strong className="text-white">import items</strong> from external sources.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ConceptCard
              icon={
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              }
              title="Export Workflow"
              description="Download your entire workflow as a .ralphx.zip file. Includes all steps, items, and resources."
              color="cyan"
            />
            <ConceptCard
              icon={
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
              }
              title="Import Workflow"
              description="Create a new workflow from a .ralphx.zip file that someone shared with you."
              color="emerald"
            />
            <ConceptCard
              icon={
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              }
              title="Import Items"
              description="Add user stories or tasks from a JSONL file. Great for bulk importing from other tools."
              color="amber"
            />
          </div>
        </div>
      </WikiSection>

      {/* Export Workflow */}
      <WikiSection
        id="export-workflow"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
        }
        title="Export a Workflow"
        description="Create a backup or share your workflow with others"
      >
        <div className="space-y-4">
          <StepGuide
            steps={[
              {
                title: 'Open your workflow',
                description: 'Go to the workflow you want to export from your project dashboard.',
              },
              {
                title: 'Click "Export Workflow"',
                description: 'Find the button in the workflow header, next to Edit and Archive.',
              },
              {
                title: 'Download the file',
                description: 'Your browser will download a .ralphx.zip file containing everything.',
              },
            ]}
          />

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
            <h4 className="text-sm font-medium text-white mb-3">What's included in the export?</h4>
            <ul className="space-y-2 text-sm text-gray-300">
              <li className="flex items-start space-x-2">
                <span className="text-cyan-400 mt-0.5">•</span>
                <span><strong className="text-white">Workflow definition</strong> - Name, steps, and configuration</span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-cyan-400 mt-0.5">•</span>
                <span><strong className="text-white">All work items</strong> - User stories, tasks, bugs</span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-cyan-400 mt-0.5">•</span>
                <span><strong className="text-white">Resources</strong> - Design docs, guardrails, instructions</span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-cyan-400 mt-0.5">•</span>
                <span><strong className="text-white">Planning sessions</strong> - Research and planning artifacts</span>
              </li>
            </ul>
          </div>

          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
            <div className="flex items-start space-x-3">
              <svg className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <h4 className="text-sm font-medium text-amber-400">Security Note</h4>
                <p className="text-sm text-gray-300 mt-1">
                  By default, RalphX automatically removes detected secrets (API keys, tokens, passwords) from exports.
                  Always review exported files before sharing publicly.
                </p>
              </div>
            </div>
          </div>

          <CopyablePrompt
            title="Export via Claude Code"
            description="You can also export workflows through Claude Code with MCP."
            prompt={`Export the workflow "my-feature" from my project as a backup file.`}
          />
        </div>
      </WikiSection>

      {/* Import Workflow */}
      <WikiSection
        id="import-workflow"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
        }
        title="Import a Workflow"
        description="Create a new workflow from a backup file"
      >
        <div className="space-y-4">
          <StepGuide
            steps={[
              {
                title: 'Go to your project dashboard',
                description: 'Navigate to the project where you want to import the workflow.',
              },
              {
                title: 'Click "Import Workflow"',
                description: 'Find the button in the Active Workflows section, next to "New Workflow". You need at least one existing workflow to see this button.',
              },
              {
                title: 'Select the .ralphx.zip file',
                description: 'Choose the file you received or downloaded earlier.',
              },
              {
                title: 'Review and confirm',
                description: 'Check the preview to see what will be imported, then click Import.',
              },
            ]}
          />

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
            <h4 className="text-sm font-medium text-white mb-3">What happens during import?</h4>
            <ul className="space-y-2 text-sm text-gray-300">
              <li className="flex items-start space-x-2">
                <span className="text-emerald-400 mt-0.5">•</span>
                <span>A <strong className="text-white">new workflow</strong> is created (doesn't overwrite existing)</span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-emerald-400 mt-0.5">•</span>
                <span>All items start fresh with <strong className="text-white">pending status</strong></span>
              </li>
              <li className="flex items-start space-x-2">
                <span className="text-emerald-400 mt-0.5">•</span>
                <span>If the name exists, a <strong className="text-white">number suffix</strong> is added automatically</span>
              </li>
            </ul>
          </div>

          <CopyablePrompt
            title="Import via Claude Code"
            description="Import a workflow backup file through Claude Code."
            prompt={`Import the workflow from the file workflow-backup.ralphx.zip into my current project.`}
          />
        </div>
      </WikiSection>

      {/* Import Items */}
      <WikiSection
        id="import-items"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        }
        title="Import Items (Advanced)"
        description="Bulk import user stories or tasks from a JSONL file"
      >
        <div className="space-y-4">
          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
            <p className="text-sm text-gray-300">
              <strong className="text-white">Most users don't need this.</strong> Claude can generate user stories
              from your design doc automatically. Item import is for power users who have stories in external
              tools or want to use predefined templates.
            </p>
          </div>

          <StepGuide
            steps={[
              {
                title: 'Open your workflow',
                description: 'Go to the workflow where you want to add items.',
              },
              {
                title: 'Go to the Items tab',
                description: 'Click the "Items" tab to see work items for this workflow.',
              },
              {
                title: 'Click "Import Items"',
                description: 'Find the button in the Items tab header.',
              },
              {
                title: 'Select your .jsonl file',
                description: 'Each line in the file should be a JSON object representing one item.',
              },
            ]}
          />

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
            <h4 className="text-sm font-medium text-white mb-3">JSONL File Format</h4>
            <p className="text-xs text-gray-400 mb-2">Each line is one item. Required: id. Highly recommended: title, content, acceptance_criteria.</p>
            <div className="bg-gray-900 rounded p-3 font-mono text-xs text-gray-300 overflow-x-auto whitespace-pre-wrap break-all">
              <div className="text-cyan-400">{'{"id": "USR-001", "title": "User login", "content": "As a user, I want to log in so I can access my account.", "priority": 1, "acceptance_criteria": ["Login form with email and password fields", "Validates credentials against database", "Shows error message for invalid credentials", "Redirects to dashboard on success"]}'}</div>
            </div>
          </div>

          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
            <div className="flex items-start space-x-3">
              <svg className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
              <div>
                <h4 className="text-sm font-medium text-amber-400">Acceptance Criteria are Important</h4>
                <p className="text-sm text-gray-300 mt-1">
                  The <code className="text-cyan-400">acceptance_criteria</code> field tells Claude how to verify each story is complete.
                  Without it, implementation may be incomplete or miss requirements. Include 2-5 testable criteria per story.
                </p>
              </div>
            </div>
          </div>

          <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700/50">
            <h4 className="text-sm font-medium text-white mb-3">Available Fields</h4>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-gray-300"><code className="text-cyan-400">id</code> - Unique identifier (required)</div>
              <div className="text-gray-300"><code className="text-cyan-400">title</code> - Short title</div>
              <div className="text-gray-300"><code className="text-cyan-400">content</code> - Full description</div>
              <div className="text-gray-300"><code className="text-cyan-400">acceptance_criteria</code> - Array of testable criteria</div>
              <div className="text-gray-300"><code className="text-cyan-400">priority</code> - 1-5 (1 = highest)</div>
              <div className="text-gray-300"><code className="text-cyan-400">category</code> - Grouping category</div>
              <div className="text-gray-300"><code className="text-cyan-400">item_type</code> - story, task, bug</div>
              <div className="text-gray-300"><code className="text-cyan-400">dependencies</code> - Array of item IDs</div>
            </div>
          </div>

          <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-lg p-4">
            <div className="flex items-start space-x-3">
              <svg className="w-5 h-5 text-cyan-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <h4 className="text-sm font-medium text-cyan-400">Duplicate Handling</h4>
                <p className="text-sm text-gray-300 mt-1">
                  If your workflow already has items, new items are added alongside them.
                  Items with duplicate IDs are skipped to prevent conflicts.
                </p>
              </div>
            </div>
          </div>

          <CopyablePrompt
            title="Import items via Claude Code"
            description="Import user stories from a JSONL file through Claude Code."
            prompt={`Import the user stories from stories.jsonl into step 1 of my "feature-workflow" workflow.`}
          />
        </div>
      </WikiSection>

      {/* Quick Reference */}
      <WikiSection
        id="quick-reference"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
        }
        title="Quick Reference"
        description="Where to find each feature"
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-700">
                <th className="text-left py-2 text-gray-400 font-medium">Action</th>
                <th className="text-left py-2 text-gray-400 font-medium">Location</th>
                <th className="text-left py-2 text-gray-400 font-medium">File Type</th>
              </tr>
            </thead>
            <tbody className="text-gray-300">
              <tr className="border-b border-gray-800">
                <td className="py-2">Export Workflow</td>
                <td className="py-2">Workflow Detail → Header</td>
                <td className="py-2"><code className="text-cyan-400">.ralphx.zip</code></td>
              </tr>
              <tr className="border-b border-gray-800">
                <td className="py-2">Import Workflow</td>
                <td className="py-2">Project Dashboard → Active Workflows</td>
                <td className="py-2"><code className="text-cyan-400">.ralphx.zip</code></td>
              </tr>
              <tr>
                <td className="py-2">Import Items</td>
                <td className="py-2">Workflow Detail → Items Tab</td>
                <td className="py-2"><code className="text-cyan-400">.jsonl</code></td>
              </tr>
            </tbody>
          </table>
        </div>
      </WikiSection>
    </div>
  )
}
