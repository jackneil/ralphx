/**
 * Help content for the RalphX application.
 * Structured by component/section for easy lookup.
 */

export interface HelpContent {
  title: string
  body: string
  learnMoreUrl?: string
}

// Dashboard help content
export const DASHBOARD_HELP: Record<string, HelpContent> = {
  projects: {
    title: 'Projects',
    body: 'A project represents a codebase or directory where you want to run AI loops. Each project can have multiple loops configured.',
  },
  addProject: {
    title: 'Add Project',
    body: 'Point RalphX at any directory on your system. The project will be created with a .ralphx configuration folder.',
  },
}

// Loop Builder help content
export const LOOP_BUILDER_HELP: Record<string, HelpContent> = {
  loopName: {
    title: 'Loop Name',
    body: 'A unique identifier for this loop. Use lowercase letters, numbers, hyphens, and underscores only. This will be used in API calls and file names.',
  },
  displayName: {
    title: 'Display Name',
    body: 'A human-readable name for this loop that will be shown in the UI.',
  },
  loopType: {
    title: 'Loop Type',
    body: 'Generator loops create new items. Consumer loops process items from other loops. Hybrid loops do both.',
  },
  itemTypes: {
    title: 'Item Types',
    body: 'Define what your loop calls its items. For example, a research loop might output "stories" while an implementation loop outputs "implementations".',
  },
  sourceLoop: {
    title: 'Source Loop',
    body: 'For consumer loops, specify which loop\'s output items to process. The source loop must exist in the same project.',
  },
  modes: {
    title: 'Modes',
    body: 'Modes define different LLM configurations. Each iteration uses one mode based on the selection strategy. You need at least one mode.',
  },
  modeModel: {
    title: 'Model',
    body: 'The AI model to use for this mode. Different models have different capabilities and costs.',
  },
  modeTimeout: {
    title: 'Timeout',
    body: 'Maximum time in seconds for a single iteration. The iteration will be stopped if it exceeds this limit.',
  },
  promptTemplate: {
    title: 'Prompt Template',
    body: 'The prompt file or inline content that defines what the AI should do in this mode. Use template variables like {{input_item}} for consumer loops.',
  },
  strategy: {
    title: 'Mode Selection Strategy',
    body: 'How to choose which mode to use for each iteration. Fixed uses one mode, Random picks randomly, Weighted Random uses probability weights.',
  },
  maxIterations: {
    title: 'Max Iterations',
    body: 'Maximum number of iterations before the loop stops. Set to 0 for unlimited (consumer loops will process all available items).',
  },
  maxRuntime: {
    title: 'Max Runtime',
    body: 'Maximum total runtime in seconds. The loop will stop after this time even if max iterations hasn\'t been reached.',
  },
  maxErrors: {
    title: 'Max Consecutive Errors',
    body: 'Stop the loop if this many iterations fail in a row. Helps prevent infinite loops when there\'s a systemic issue.',
  },
  cooldown: {
    title: 'Cooldown',
    body: 'Seconds to wait between iterations. Useful for rate limiting or allowing external processes to complete.',
  },
}

// Items page help content
export const ITEMS_HELP: Record<string, HelpContent> = {
  status: {
    title: 'Item Status',
    body: 'Pending items are waiting to be processed. In Progress items are currently being worked on. Completed items are ready for consumers. Processed items have been consumed.',
  },
  sourceLoop: {
    title: 'Source Loop',
    body: 'The loop that created this item. Consumer loops can only see items from their configured source loop.',
  },
  claimed: {
    title: 'Claimed',
    body: 'When a consumer loop starts processing an item, it claims it to prevent other consumers from picking it up.',
  },
}

// Loop status help content
export const LOOP_STATUS_HELP: Record<string, HelpContent> = {
  running: {
    title: 'Running',
    body: 'The loop is actively processing iterations. You can pause or stop it at any time.',
  },
  paused: {
    title: 'Paused',
    body: 'The loop is temporarily stopped but can be resumed. The current iteration state is preserved.',
  },
  stopped: {
    title: 'Stopped',
    body: 'The loop has completed or been stopped. Start it again to begin a new run.',
  },
}

// Project detail help content
export const PROJECT_HELP: Record<string, HelpContent> = {
  designDoc: {
    title: 'Design Document',
    body: 'An optional document describing your project. AI loops can reference this for context about your codebase.',
  },
  stats: {
    title: 'Project Stats',
    body: 'Overview of items and loops in this project. Active runs shows how many loops are currently running.',
  },
}

// Template help content
export const TEMPLATE_HELP: Record<string, HelpContent> = {
  research: {
    title: 'Research Loop',
    body: 'Discovers and documents user stories from design documents. Uses two modes: fast extraction and deep research.',
  },
  implementation: {
    title: 'Implementation Loop',
    body: 'Consumes stories from a research loop and implements them with test verification.',
  },
  simpleGenerator: {
    title: 'Simple Generator',
    body: 'A basic loop for generating content items. Good starting point for custom generators.',
  },
  reviewer: {
    title: 'Review Loop',
    body: 'Processes existing items for review, validation, or transformation. Consumes from another loop.',
  },
}
