/**
 * Utility functions for validating custom AI instructions (prompts)
 * in workflow steps.
 */

import type { TemplateVariableInfo } from '../api'

// Template variables that are required for each loop type
const REQUIRED_VARIABLES: Record<string, string[]> = {
  generator: ['{{existing_stories}}'],
  consumer: ['{{input_item.title}}', '{{input_item.content}}'],
}

// All known template variables for each loop type
const ALL_VARIABLES: Record<string, string[]> = {
  generator: [
    '{{existing_stories}}',
    '{{total_stories}}',
    '{{category_stats}}',
    '{{inputs_list}}',
    '{{input_item.title}}',
  ],
  consumer: [
    '{{input_item.title}}',
    '{{input_item.content}}',
    '{{input_item.metadata}}',
    '{{implemented_summary}}',
  ],
}

export interface PromptValidationResult {
  isValid: boolean
  missingRequired: string[]
  missingOptional: string[]
  warnings: string[]
}

/**
 * Validate a custom prompt against required template variables.
 *
 * @param prompt - The custom prompt text to validate
 * @param loopType - The loop type ('generator' or 'consumer')
 * @param variableInfo - Optional variable info from the API
 * @returns Validation result with missing variables and warnings
 */
export function validatePrompt(
  prompt: string,
  loopType: string,
  variableInfo?: TemplateVariableInfo[]
): PromptValidationResult {
  const result: PromptValidationResult = {
    isValid: true,
    missingRequired: [],
    missingOptional: [],
    warnings: [],
  }

  if (!prompt || !prompt.trim()) {
    return result // Empty prompts are valid (will use default)
  }

  // Use API-provided variable info if available, otherwise use local definitions
  let requiredVars: string[]
  let allVars: string[]

  if (variableInfo && variableInfo.length > 0) {
    requiredVars = variableInfo
      .filter((v) => v.required)
      .map((v) => v.name)
    allVars = variableInfo.map((v) => v.name)
  } else {
    requiredVars = REQUIRED_VARIABLES[loopType] || []
    allVars = ALL_VARIABLES[loopType] || []
  }

  // Check for missing required variables
  for (const variable of requiredVars) {
    if (!prompt.includes(variable)) {
      result.missingRequired.push(variable)
      result.isValid = false
    }
  }

  // Check for missing optional variables
  for (const variable of allVars) {
    if (!requiredVars.includes(variable) && !prompt.includes(variable)) {
      result.missingOptional.push(variable)
    }
  }

  // Generate warnings
  if (result.missingRequired.length > 0) {
    result.warnings.push(
      `Missing required template variable${result.missingRequired.length > 1 ? 's' : ''}: ${result.missingRequired.join(', ')}. The step may not work correctly.`
    )
  }

  if (result.missingOptional.length > 0 && result.missingOptional.length <= 2) {
    result.warnings.push(
      `Optional variable${result.missingOptional.length > 1 ? 's' : ''} not used: ${result.missingOptional.join(', ')}`
    )
  }

  return result
}

/**
 * Get a user-friendly description for a loop type.
 */
export function getLoopTypeLabel(loopType: string): string {
  const labels: Record<string, string> = {
    generator: 'Generator (Story Extraction)',
    consumer: 'Consumer (Implementation)',
    design_doc: 'Design Document (Interactive)',
  }
  return labels[loopType] || loopType
}

/**
 * Check if a prompt has been meaningfully modified from the default.
 */
export function isPromptModified(
  customPrompt: string | undefined,
  defaultPrompt: string
): boolean {
  if (!customPrompt || !customPrompt.trim()) {
    return false
  }
  // Normalize whitespace for comparison
  const normalizedCustom = customPrompt.trim().replace(/\s+/g, ' ')
  const normalizedDefault = defaultPrompt.trim().replace(/\s+/g, ' ')
  return normalizedCustom !== normalizedDefault
}
