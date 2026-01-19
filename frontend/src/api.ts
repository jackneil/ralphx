const API_BASE = '/api'

class APIError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string
  ) {
    super(message)
    this.name = 'APIError'
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    const message = errorData.error?.message || errorData.detail || response.statusText
    throw new APIError(message, response.status, errorData.error?.code)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json()
}

// Health
export async function getHealth() {
  return request<{ status: string; version: string; timestamp: string }>('/health')
}

// Projects
export async function listProjects() {
  return request<{
    id: string
    slug: string
    name: string
    path: string
    design_doc?: string
    created_at: string
  }[]>('/projects')
}

export async function getProject(slug: string) {
  return request<{
    id: string
    slug: string
    name: string
    path: string
    design_doc?: string
    created_at: string
    stats: {
      total_items: number
      pending_items: number
      completed_items: number
      loops: number
      active_runs: number
    }
  }>(`/projects/${slug}`)
}

export async function createProject(data: { path: string; name?: string; design_doc?: string }) {
  return request<{
    id: string
    slug: string
    name: string
    path: string
    created_at: string
  }>('/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteProject(slug: string) {
  return request<void>(`/projects/${slug}`, { method: 'DELETE' })
}

export async function cleanupProjects(pattern: string = '^e2e-', dryRun: boolean = true) {
  return request<{
    deleted: string[]
    failed: string[]
    dry_run: boolean
  }>('/projects/cleanup', {
    method: 'POST',
    body: JSON.stringify({ pattern, dry_run: dryRun }),
  })
}

// Item Types
export interface ItemTypeConfig {
  singular: string
  plural: string
  description?: string
  source?: string
}

export interface ItemTypes {
  input?: ItemTypeConfig
  output: ItemTypeConfig
}

// Loops
export async function listLoops(slug: string) {
  return request<{
    name: string
    display_name: string
    type: string
    modes: string[]
    item_types?: ItemTypes
    workflow_id?: string  // Optional - legacy loops may not have this
    step_id?: number
  }[]>(`/projects/${slug}/loops`)
}

export async function getLoop(slug: string, loopName: string) {
  return request<{
    name: string
    display_name: string
    type: string
    modes: { name: string; model: string; timeout: number }[]
    item_types?: ItemTypes
  }>(`/projects/${slug}/loops/${loopName}`)
}

export async function getLoopStatus(slug: string, loopName: string) {
  return request<{
    loop_name: string
    is_running: boolean
    run_id?: string
    current_iteration?: number
    current_mode?: string
    status?: string
  }>(`/projects/${slug}/loops/${loopName}/status`)
}

export interface StartLoopOptions {
  mode?: string
  iterations?: number
  force?: boolean
  phase?: number
  category?: string
  respect_dependencies?: boolean
  batch_mode?: boolean
  batch_size?: number
}

export async function startLoop(
  slug: string,
  loopName: string,
  options?: StartLoopOptions
) {
  return request<{ message: string; run_id: string }>(`/projects/${slug}/loops/${loopName}/start`, {
    method: 'POST',
    body: JSON.stringify(options || {}),
  })
}

export interface PhaseInfo {
  phase_number: number
  item_count: number
  item_ids: string[]
  categories: string[]
  pending_count: number
  completed_count: number
}

export interface CategoryInfo {
  name: string
  item_count: number
  pending_count: number
  completed_count: number
}

export interface PhaseInfoResponse {
  loop_name: string
  workflow_id: string | null
  source_step_id: number | null
  total_items: number
  phases: PhaseInfo[]
  categories: CategoryInfo[]
  has_dependencies: boolean
  has_cycles: boolean
  graph_stats: Record<string, number>
  warnings: string[]
}

export async function getLoopPhases(slug: string, loopName: string) {
  return request<PhaseInfoResponse>(`/projects/${slug}/loops/${loopName}/phases`)
}

export async function stopLoop(slug: string, loopName: string) {
  return request<{ message: string }>(`/projects/${slug}/loops/${loopName}/stop`, {
    method: 'POST',
  })
}

export async function pauseLoop(slug: string, loopName: string) {
  return request<{ message: string }>(`/projects/${slug}/loops/${loopName}/pause`, {
    method: 'POST',
  })
}

export async function resumeLoop(slug: string, loopName: string) {
  return request<{ message: string }>(`/projects/${slug}/loops/${loopName}/resume`, {
    method: 'POST',
  })
}

export async function deleteLoop(slug: string, loopName: string) {
  return request<void>(`/projects/${slug}/loops/${loopName}`, {
    method: 'DELETE',
  })
}

export async function getLoopConfig(slug: string, loopName: string) {
  return request<{ content: string; path: string }>(`/projects/${slug}/loops/${loopName}/config`)
}

export async function updateLoopConfig(slug: string, loopName: string, content: string) {
  return request<{ message: string; path: string }>(`/projects/${slug}/loops/${loopName}/config`, {
    method: 'PUT',
    body: JSON.stringify({ content }),
  })
}

export async function createLoop(slug: string, name: string, content: string) {
  return request<{
    message: string
    path: string
    loop: {
      name: string
      display_name: string
      type: string
      item_types?: ItemTypes
    }
  }>(`/projects/${slug}/loops`, {
    method: 'POST',
    body: JSON.stringify({ name, content }),
  })
}

// Items (Work Items)
export interface Item {
  id: string
  workflow_id: string
  source_step_id: number
  content: string
  title?: string
  status: string
  category?: string
  priority?: number
  item_type?: string
  claimed_by?: string
  claimed_at?: string
  processed_at?: string
  created_at: string
  updated_at: string
  metadata?: Record<string, unknown>
  // Phase and dependency fields
  dependencies?: string[]
  phase?: number
  duplicate_of?: string
  skip_reason?: string
  tags?: string[]
}

export async function listItems(
  slug: string,
  params?: {
    status?: string
    category?: string
    workflow_id?: string
    source_step_id?: number
    limit?: number
    offset?: number
  }
) {
  const searchParams = new URLSearchParams()
  if (params?.status) searchParams.set('status', params.status)
  if (params?.category) searchParams.set('category', params.category)
  if (params?.workflow_id) searchParams.set('workflow_id', params.workflow_id)
  if (params?.source_step_id) searchParams.set('source_step_id', params.source_step_id.toString())
  if (params?.limit) searchParams.set('limit', params.limit.toString())
  if (params?.offset) searchParams.set('offset', params.offset.toString())

  const query = searchParams.toString()
  return request<{
    items: Item[]
    total: number
    limit: number
    offset: number
  }>(`/projects/${slug}/items${query ? `?${query}` : ''}`)
}

export async function getItem(slug: string, itemId: string) {
  return request<Item>(`/projects/${slug}/items/${itemId}`)
}

export async function createItem(
  slug: string,
  data: {
    content: string
    workflow_id: string
    source_step_id: number
    title?: string
    category?: string
    priority?: number
    dependencies?: string[]
    metadata?: Record<string, unknown>
  }
) {
  return request<{
    id: string
    content: string
    title?: string
    status: string
    created_at: string
  }>(`/projects/${slug}/items`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateItem(
  slug: string,
  itemId: string,
  data: {
    content?: string
    title?: string
    status?: string
    category?: string
    priority?: number
    dependencies?: string[]
    metadata?: Record<string, unknown>
  }
) {
  return request<{
    id: string
    content: string
    title?: string
    status: string
    updated_at: string
  }>(`/projects/${slug}/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function duplicateItem(
  slug: string,
  itemId: string,
  overrides?: {
    title?: string
    content?: string
    category?: string
    priority?: number
    dependencies?: string[]
  }
) {
  // Fetch the original item
  const original = await getItem(slug, itemId)

  // Create a new item with original data + overrides
  return createItem(slug, {
    workflow_id: original.workflow_id,
    source_step_id: original.source_step_id,
    title: overrides?.title ?? (original.title ? `${original.title} (copy)` : undefined),
    content: overrides?.content ?? original.content,
    category: overrides?.category ?? original.category,
    priority: overrides?.priority ?? original.priority,
    dependencies: overrides?.dependencies ?? original.dependencies,
    metadata: original.metadata,
  })
}

export async function deleteItem(slug: string, itemId: string) {
  return request<void>(`/projects/${slug}/items/${itemId}`, { method: 'DELETE' })
}

export async function getItemsStats(slug: string) {
  return request<{
    total: number
    by_status: Record<string, number>
    by_category: Record<string, number>
    by_priority: Record<number, number>
  }>(`/projects/${slug}/items/stats`)
}

// Sessions
export async function listSessions(slug: string, runId?: string) {
  const params = runId ? `?run_id=${runId}` : ''
  return request<{
    session_id: string
    project_id: string
    run_id?: string
    iteration: number
    mode?: string
    status: string
    started_at?: string
    duration_seconds?: number
  }[]>(`/projects/${slug}/sessions${params}`)
}

// Filesystem
export async function browseDirectory(path?: string) {
  const params = path ? `?path=${encodeURIComponent(path)}` : ''
  return request<{
    path: string
    directories: string[]
    canGoUp: boolean
    parent: string | null
  }>(`/filesystem/browse${params}`)
}

// Ready Check (Pre-Flight Clarification)
export interface ReadyCheckQuestion {
  id: string
  category: string
  question: string
  context?: string
}

export interface ReadyCheckAnswer {
  question_id: string
  answer: string
}

export interface ReadyCheckStatus {
  has_qa: boolean
  qa_count: number
  last_updated?: string
  qa_summary: string[]
  resource_id?: number
}

export interface ReadyCheckTriggerResponse {
  status: 'analyzing' | 'questions' | 'ready'
  questions: ReadyCheckQuestion[]
  assessment?: string
  session_id?: string
}

export async function getReadyCheckStatus(slug: string, loopName: string) {
  return request<ReadyCheckStatus>(`/projects/${slug}/loops/${loopName}/ready-check`)
}

export async function triggerReadyCheck(slug: string, loopName: string) {
  return request<ReadyCheckTriggerResponse>(`/projects/${slug}/loops/${loopName}/ready-check`, {
    method: 'POST',
  })
}

export async function submitReadyCheckAnswers(
  slug: string,
  loopName: string,
  questions: ReadyCheckQuestion[],
  answers: ReadyCheckAnswer[]
) {
  return request<{
    saved: boolean
    resource_id?: number
    can_start: boolean
  }>(`/projects/${slug}/loops/${loopName}/ready-check/answers`, {
    method: 'POST',
    body: JSON.stringify({ questions, answers }),
  })
}

// Runs
export async function listRuns(slug: string, loopName?: string) {
  const params = loopName ? `?loop_name=${encodeURIComponent(loopName)}` : ''
  return request<{
    id: string
    project_id: string
    loop_name: string
    status: string
    iterations_completed: number
    items_processed: number
    started_at: string
    ended_at?: string
  }[]>(`/projects/${slug}/runs${params}`)
}

export async function getRun(slug: string, runId: string) {
  return request<{
    id: string
    project_id: string
    loop_name: string
    status: string
    iterations_completed: number
    items_processed: number
    started_at: string
    ended_at?: string
    sessions: {
      session_id: string
      iteration: number
      mode?: string
      status: string
      started_at?: string
      duration_seconds?: number
    }[]
  }>(`/projects/${slug}/runs/${runId}`)
}

// Templates
export interface TemplateListItem {
  name: string
  display_name: string
  description: string
  type: string
  category: string
}

export interface TemplateDetail extends TemplateListItem {
  config: Record<string, unknown>
  config_yaml: string
}

export async function listTemplates() {
  return request<{ templates: TemplateListItem[] }>('/templates')
}

export async function getTemplate(name: string) {
  return request<TemplateDetail>(`/templates/${name}`)
}

export async function getTemplateYaml(name: string) {
  return request<{ yaml: string }>(`/templates/${name}/yaml`)
}

// Loop Templates
export interface LoopTemplateInfo {
  id: string
  name: string
  description: string
}

export interface LoopTemplateDetail extends LoopTemplateInfo {
  config: string
  prompts: Record<string, string>
  permission_template?: string
}

export async function listLoopTemplates() {
  return request<LoopTemplateInfo[]>('/loop-templates')
}

export async function getLoopTemplate(templateId: string) {
  return request<LoopTemplateDetail>(`/loop-templates/${templateId}`)
}

export async function createLoopFromTemplate(
  slug: string,
  loopName: string,
  templateId: string,
  displayName?: string
) {
  return request<{
    message: string
    loop_name: string
    loop_dir: string
  }>(`/projects/${slug}/loops/from-template`, {
    method: 'POST',
    body: JSON.stringify({
      loop_name: loopName,
      template_id: templateId,
      display_name: displayName,
    }),
  })
}

// Permission Templates
export interface PermissionTemplateInfo {
  id: string
  name: string
  description: string
}

export interface PermissionTemplateDetail extends PermissionTemplateInfo {
  settings: Record<string, unknown>
}

export async function listPermissionTemplates() {
  return request<PermissionTemplateInfo[]>('/projects/permission-templates')
}

export async function getPermissionTemplate(templateId: string) {
  return request<PermissionTemplateDetail>(`/projects/permission-templates/${templateId}`)
}

export async function applyPermissionTemplate(
  slug: string,
  loopName: string,
  templateId: string
) {
  return request<{
    message: string
    settings_path: string
  }>(`/projects/${slug}/loops/${loopName}/apply-permissions`, {
    method: 'POST',
    body: JSON.stringify({ template_id: templateId }),
  })
}

// Loop Permissions
export interface LoopPermissions {
  has_custom: boolean
  source: 'custom' | 'template' | 'default'
  permissions: {
    allow: string[]
    deny?: string[]
  }
  settings_path: string
  template_id?: string
}

export async function getLoopPermissions(
  slug: string,
  loopName: string
): Promise<LoopPermissions> {
  return request<LoopPermissions>(`/projects/${slug}/loops/${loopName}/permissions`)
}

export async function updateLoopPermissions(
  slug: string,
  loopName: string,
  data: {
    permissions?: { allow: string[]; deny?: string[] }
    template_id?: string
  }
): Promise<LoopPermissions> {
  return request<LoopPermissions>(`/projects/${slug}/loops/${loopName}/permissions`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function deleteLoopPermissions(
  slug: string,
  loopName: string
): Promise<void> {
  return request<void>(`/projects/${slug}/loops/${loopName}/permissions`, {
    method: 'DELETE',
  })
}

// Loop Inputs (Imports)
export interface InputFileInfo {
  name: string
  path: string
  size: number
  modified: string
  tag?: string
}

export async function listLoopInputs(slug: string, loopName: string) {
  return request<InputFileInfo[]>(`/projects/${slug}/loops/${loopName}/inputs`)
}

export async function uploadLoopInput(
  slug: string,
  loopName: string,
  file: File
) {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(
    `${API_BASE}/projects/${slug}/loops/${loopName}/inputs/upload`,
    {
      method: 'POST',
      body: formData,
    }
  )

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    const message = errorData.error?.message || errorData.detail || response.statusText
    throw new APIError(message, response.status, errorData.error?.code)
  }

  return response.json()
}

export async function importPasteToLoop(
  slug: string,
  loopName: string,
  content: string,
  filename: string,
  tag?: string
) {
  return request<{
    success: boolean
    files_imported: number
    paths: string[]
    errors: string[]
  }>(`/projects/${slug}/loops/${loopName}/inputs/paste`, {
    method: 'POST',
    body: JSON.stringify({ content, filename, tag }),
  })
}

export async function getLoopInputContent(
  slug: string,
  loopName: string,
  filename: string
) {
  return request<{ filename: string; content: string }>(
    `/projects/${slug}/loops/${loopName}/inputs/${encodeURIComponent(filename)}`
  )
}

export async function deleteLoopInput(
  slug: string,
  loopName: string,
  filename: string
) {
  return request<{ message: string }>(
    `/projects/${slug}/loops/${loopName}/inputs/${encodeURIComponent(filename)}`,
    { method: 'DELETE' }
  )
}

// Loop Preview
export interface PromptSection {
  position: string
  source: string
  source_name?: string
  content: string
  start_line: number
  end_line: number
}

export interface ModePreview {
  mode_name: string
  model: string
  timeout: number
  tools: string[]
  total_length: number
  token_estimate: number
  sections: PromptSection[]
  rendered_prompt: string
  warnings: string[]
}

export interface PreviewResponse {
  loop_name: string
  loop_type: string
  mode_selection_strategy: string
  strategy_explanation: string
  sample_item?: Record<string, unknown>
  modes: ModePreview[]
  resources_used: string[]
  guardrails_used: string[]
  template_variables: Record<string, string>
  warnings: string[]
}

export interface PreviewOptions {
  mode?: string
  sample_item_id?: string
  use_first_pending?: boolean
  include_annotations?: boolean
}

export async function previewLoopPrompt(
  slug: string,
  loopName: string,
  options?: PreviewOptions
) {
  return request<PreviewResponse>(`/projects/${slug}/loops/${loopName}/preview`, {
    method: 'POST',
    body: JSON.stringify(options || {}),
  })
}

// Project Resources
export interface Resource {
  id: number
  name: string
  resource_type: string
  file_path: string
  injection_position: string
  enabled: boolean
  inherit_default: boolean
  priority: number
  created_at?: string
  updated_at?: string
  content?: string
}

export async function listResources(slug: string, params?: {
  resource_type?: string
  enabled?: boolean
  include_content?: boolean
}) {
  const searchParams = new URLSearchParams()
  if (params?.resource_type) searchParams.set('resource_type', params.resource_type)
  if (params?.enabled !== undefined) searchParams.set('enabled', params.enabled.toString())
  if (params?.include_content !== undefined) searchParams.set('include_content', params.include_content.toString())

  const query = searchParams.toString()
  return request<Resource[]>(`/projects/${slug}/resources${query ? `?${query}` : ''}`)
}

export async function getResource(slug: string, resourceId: number, includeContent: boolean = true) {
  const params = includeContent ? '?include_content=true' : ''
  return request<Resource>(`/projects/${slug}/resources/${resourceId}${params}`)
}

export async function createResource(
  slug: string,
  data: {
    name: string
    resource_type: string
    content: string
    injection_position?: string
  }
) {
  return request<Resource>(`/projects/${slug}/resources`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateResource(
  slug: string,
  resourceId: number,
  data: {
    content?: string
    injection_position?: string
    enabled?: boolean
    inherit_default?: boolean
    priority?: number
  }
) {
  return request<Resource>(`/projects/${slug}/resources/${resourceId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteResource(slug: string, resourceId: number, deleteFile: boolean = true) {
  const params = deleteFile ? '' : '?delete_file=false'
  return request<void>(`/projects/${slug}/resources/${resourceId}${params}`, {
    method: 'DELETE',
  })
}

export async function syncResources(slug: string) {
  return request<{ added: number; updated: number; removed: number }>(
    `/projects/${slug}/resources/sync`,
    { method: 'POST' }
  )
}

export async function getResourceTypes() {
  return request<{
    types: { value: string; label: string }[]
    positions: { value: string; label: string }[]
  }>('/projects/_/resources/types')
}

// Project File Browsing
export interface ProjectFile {
  name: string
  size: number
  extension: string
}

export interface BrowseFilesResponse {
  path: string
  relative_path: string
  directories: string[]
  files: ProjectFile[]
  canGoUp: boolean
  parent: string | null
  hidden_count: number
  other_files_count: number
}

export interface FileContentResponse {
  path: string
  filename: string
  content: string
  size: number
}

export async function browseProjectFiles(slug: string, path?: string): Promise<BrowseFilesResponse> {
  const params = path ? `?path=${encodeURIComponent(path)}` : ''
  return request<BrowseFilesResponse>(`/projects/${slug}/files/browse${params}`)
}

export async function readProjectFile(slug: string, path: string): Promise<FileContentResponse> {
  return request<FileContentResponse>(`/projects/${slug}/files/read?path=${encodeURIComponent(path)}`)
}

// Input Templates
export interface InputTemplateInfo {
  id: string
  name: string
  description: string
  loop_type: string
  tag: string
  filename: string
}

export interface InputTemplateDetail extends InputTemplateInfo {
  content: string
}

export interface InputTag {
  label: string
  description: string
}

export interface ValidationResult {
  valid: boolean
  missing_tags: string[]
  warnings: string[]
}

export async function listInputTemplates(loopType?: string) {
  const params = loopType ? `?loop_type=${encodeURIComponent(loopType)}` : ''
  return request<InputTemplateInfo[]>(`/projects/input-templates${params}`)
}

export async function getInputTemplate(templateId: string) {
  return request<InputTemplateDetail>(`/projects/input-templates/${encodeURIComponent(templateId)}`)
}

export async function listInputTags() {
  return request<Record<string, InputTag>>('/projects/input-tags')
}

export async function applyInputTemplate(
  slug: string,
  loopName: string,
  templateId: string,
  customFilename?: string
) {
  return request<{
    success: boolean
    files_imported: number
    paths: string[]
    errors: string[]
  }>(`/projects/${slug}/loops/${loopName}/inputs/apply-template`, {
    method: 'POST',
    body: JSON.stringify({
      template_id: templateId,
      custom_filename: customFilename,
    }),
  })
}

export async function validateLoopInputs(
  slug: string,
  loopName: string,
  loopType: string
) {
  return request<ValidationResult>(
    `/projects/${slug}/loops/${loopName}/inputs/validate?loop_type=${encodeURIComponent(loopType)}`
  )
}

export async function updateInputTag(
  slug: string,
  loopName: string,
  filename: string,
  tag: string | null
) {
  return request<{ filename: string; tag: string | null }>(
    `/projects/${slug}/loops/${loopName}/inputs/${encodeURIComponent(filename)}`,
    {
      method: 'PATCH',
      body: JSON.stringify({ tag }),
    }
  )
}

// Simple Loop Creation (Wizard)
export interface SimpleLoopRequest {
  type: 'planning' | 'implementation'

  // User-facing name and description (ID is auto-generated by backend)
  display_name?: string  // Defaults to "Planning" or "Implementation"
  description?: string   // Optional description

  // Planning fields
  design_doc?: {
    content: string
    filename: string
  }
  use_default_instructions?: boolean
  use_default_guardrails?: boolean

  // Implementation fields
  stories_source?: {
    type: 'loop' | 'content'
    loop_name?: string
    content?: string
    filename?: string
  }
  design_context?: {
    content: string
    filename: string
  }
  use_code_guardrails?: boolean
}

export interface SimpleLoopResponse {
  loop_id: string        // Auto-generated unique ID
  display_name: string   // User-facing name
  loop_dir: string
  inputs_created: string[]
  message: string
}

export async function createSimpleLoop(
  slug: string,
  data: SimpleLoopRequest
) {
  return request<SimpleLoopResponse>(`/projects/${slug}/loops/simple`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// Auth types
export interface AuthStatus {
  connected: boolean
  scope?: 'project' | 'global'
  email?: string
  subscription_type?: string
  rate_limit_tier?: string
  expires_at?: string
  expires_in_seconds?: number
  is_expired: boolean
  using_global_fallback: boolean
  has_project_credentials: boolean
}

export interface LoginRequest {
  scope: 'project' | 'global'
  project_path?: string
}

// Auth API functions
export async function getAuthStatus(projectPath?: string): Promise<AuthStatus> {
  const params = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : ''
  return request<AuthStatus>(`/auth/status${params}`)
}

export async function startLogin(req: LoginRequest): Promise<{ success: boolean; message?: string; error?: string }> {
  return request('/auth/login', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export async function logoutAuth(req: LoginRequest): Promise<{ success: boolean }> {
  return request('/auth/logout', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export async function refreshAuthToken(req: LoginRequest): Promise<{ success: boolean; message?: string; error?: string; needs_relogin?: boolean }> {
  return request('/auth/refresh', {
    method: 'POST',
    body: JSON.stringify(req),
  })
}

export interface CredentialsExport {
  success: boolean
  error?: string
  scope?: string
  email?: string
  credentials?: {
    claudeAiOauth: {
      accessToken: string
      refreshToken: string
      expiresAt: number
    }
  }
}

export async function exportCredentials(
  scope: 'project' | 'global' = 'global',
  projectPath?: string
): Promise<CredentialsExport> {
  const params = new URLSearchParams({ scope })
  if (projectPath) params.set('project_path', projectPath)
  return request<CredentialsExport>(`/auth/credentials/export?${params}`)
}

export interface AuthValidationResult {
  valid: boolean
  error?: string
  scope?: string
  email?: string
  refreshed?: boolean
}

export async function validateAuth(projectPath?: string): Promise<AuthValidationResult> {
  const params = projectPath ? `?project_path=${encodeURIComponent(projectPath)}` : ''
  return request<AuthValidationResult>(`/auth/validate${params}`)
}

// ============================================================================
// Logs API
// ============================================================================

export interface LogEntry {
  id: number
  level: string
  category: string | null
  event: string | null
  message: string
  project_id: string | null
  run_id: string | null
  metadata: Record<string, unknown> | null
  timestamp: string
}

export interface LogsResponse {
  logs: LogEntry[]
  total: number
  limit: number
  offset: number
}

export interface LogStats {
  total: number
  by_level: Record<string, number>
  by_category: Record<string, number>
  recent_errors_24h: number
}

export interface LogFilters {
  level?: string
  category?: string
  event?: string
  project_id?: string
  run_id?: string
  since?: string
  until?: string
  limit?: number
  offset?: number
}

export async function getLogs(filters: LogFilters = {}): Promise<LogsResponse> {
  const params = new URLSearchParams()
  if (filters.level) params.set('level', filters.level)
  if (filters.category) params.set('category', filters.category)
  if (filters.event) params.set('event', filters.event)
  if (filters.project_id) params.set('project_id', filters.project_id)
  if (filters.run_id) params.set('run_id', filters.run_id)
  if (filters.since) params.set('since', filters.since)
  if (filters.until) params.set('until', filters.until)
  if (filters.limit) params.set('limit', String(filters.limit))
  if (filters.offset) params.set('offset', String(filters.offset))
  return request<LogsResponse>(`/logs?${params}`)
}

export async function getLogStats(): Promise<LogStats> {
  return request<LogStats>('/logs/stats')
}

export async function cleanupLogs(days: number = 30): Promise<{ deleted: number; days: number }> {
  return request<{ deleted: number; days: number }>(`/logs?days=${days}`, {
    method: 'DELETE',
  })
}

// ============================================================================
// Loop Resources API (per-loop resources)
// ============================================================================

export interface LoopResource {
  id: number
  loop_name: string
  resource_type: 'loop_template' | 'design_doc' | 'guardrails' | 'custom'
  name: string
  injection_position: 'template_body' | 'before_prompt' | 'after_design_doc' | 'before_task' | 'after_task'
  source_type: 'system' | 'project_file' | 'loop_ref' | 'project_resource' | 'inline'
  source_path?: string | null
  source_loop?: string | null
  source_resource_id?: number | null
  enabled: boolean
  priority: number
  created_at?: string
  content?: string | null
}

export interface CreateLoopResourceRequest {
  resource_type: string
  name: string
  injection_position?: string
  source_type: string
  source_path?: string
  source_loop?: string
  source_resource_id?: number
  inline_content?: string
  enabled?: boolean
  priority?: number
}

export interface UpdateLoopResourceRequest {
  name?: string
  injection_position?: string
  source_type?: string
  source_path?: string
  source_loop?: string
  source_resource_id?: number
  inline_content?: string
  enabled?: boolean
  priority?: number
}

export async function listLoopResources(
  slug: string,
  loopName: string,
  includeContent: boolean = false
): Promise<LoopResource[]> {
  const params = includeContent ? '?include_content=true' : ''
  return request<LoopResource[]>(`/projects/${slug}/loops/${loopName}/resources${params}`)
}

export async function getLoopResource(
  slug: string,
  loopName: string,
  resourceId: number,
  includeContent: boolean = true
): Promise<LoopResource> {
  const params = includeContent ? '?include_content=true' : ''
  return request<LoopResource>(`/projects/${slug}/loops/${loopName}/resources/${resourceId}${params}`)
}

export async function createLoopResource(
  slug: string,
  loopName: string,
  data: CreateLoopResourceRequest
): Promise<LoopResource> {
  return request<LoopResource>(`/projects/${slug}/loops/${loopName}/resources`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateLoopResource(
  slug: string,
  loopName: string,
  resourceId: number,
  data: UpdateLoopResourceRequest
): Promise<LoopResource> {
  return request<LoopResource>(`/projects/${slug}/loops/${loopName}/resources/${resourceId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteLoopResource(
  slug: string,
  loopName: string,
  resourceId: number
): Promise<void> {
  return request<void>(`/projects/${slug}/loops/${loopName}/resources/${resourceId}`, {
    method: 'DELETE',
  })
}

// ============================================================================
// Workflows API
// ============================================================================

// Item status breakdown for workflow steps
export interface ItemStatusBreakdown {
  total: number
  pending: number
  in_progress: number
  completed: number
  skipped: number
  failed: number
  duplicate: number
  rejected: number
}

export interface WorkflowStep {
  id: number
  workflow_id: string
  step_number: number
  name: string
  step_type: 'interactive' | 'autonomous'
  status: 'pending' | 'active' | 'completed' | 'skipped'
  config?: {
    description?: string
    loopType?: string
    model?: 'sonnet' | 'opus' | 'haiku' | 'sonnet-1m'
    timeout?: number
    allowedTools?: string[]
    inputs?: string[]
    outputs?: string[]
    skippable?: boolean
    skipCondition?: string
    architecture_first?: boolean
    // Loop limits (autonomous steps only)
    max_iterations?: number
    cooldown_between_iterations?: number
    max_consecutive_errors?: number
  }
  loop_name?: string
  artifacts?: Record<string, unknown>
  started_at?: string
  completed_at?: string
  archived_at?: string | null  // NULL = active, non-NULL = archived (soft delete)
  has_active_run?: boolean  // True if there's a run in 'running' status
  // Progress tracking
  iterations_completed?: number  // Total iterations completed across all runs
  iterations_target?: number | null  // Target iterations (from config), null = unlimited
  current_run_iterations?: number  // Iterations in current/latest run
  items_generated?: number  // Total items generated (e.g., user stories)
  has_guardrails?: boolean  // Whether this step has guardrails configured
  // Input items breakdown (for consumer steps)
  input_items?: ItemStatusBreakdown  // Status breakdown of items from source step
}

export interface Workflow {
  id: string
  template_id?: string
  name: string
  namespace: string
  status: 'draft' | 'active' | 'paused' | 'completed'
  current_step: number
  created_at: string
  updated_at: string
  archived_at?: string | null  // NULL = active, non-NULL = archived timestamp
  steps: WorkflowStep[]
  // Resource indicators
  has_design_doc?: boolean  // Whether workflow has a design document
  guardrails_count?: number  // Number of guardrails attached
}

export interface WorkflowTemplateStep {
  number: number
  name: string
  type: 'interactive' | 'autonomous'
  description?: string
  loopType?: string
  inputs?: string[]
  outputs?: string[]
  skippable?: boolean
  skipCondition?: string
}

export interface WorkflowTemplate {
  id: string
  name: string
  description?: string
  steps: WorkflowTemplateStep[]
  created_at: string
}

export async function listWorkflowTemplates(slug: string): Promise<WorkflowTemplate[]> {
  return request<WorkflowTemplate[]>(`/projects/${slug}/workflow-templates`)
}

export async function getWorkflowTemplate(slug: string, templateId: string): Promise<WorkflowTemplate> {
  return request<WorkflowTemplate>(`/projects/${slug}/workflow-templates/${templateId}`)
}

export async function listWorkflows(
  slug: string,
  options?: {
    status?: string
    include_archived?: boolean
    archived_only?: boolean
  }
): Promise<Workflow[]> {
  const searchParams = new URLSearchParams()
  if (options?.status) searchParams.set('status_filter', options.status)
  if (options?.include_archived) searchParams.set('include_archived', 'true')
  if (options?.archived_only) searchParams.set('archived_only', 'true')
  const query = searchParams.toString()
  return request<Workflow[]>(`/projects/${slug}/workflows${query ? `?${query}` : ''}`)
}

export async function getWorkflow(slug: string, workflowId: string): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}`)
}

export async function createWorkflow(
  slug: string,
  data: { name: string; template_id?: string; config?: { architecture_first?: boolean } }
): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateWorkflow(
  slug: string,
  workflowId: string,
  data: { name?: string; status?: string }
): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function deleteWorkflow(slug: string, workflowId: string): Promise<void> {
  return request<void>(`/projects/${slug}/workflows/${workflowId}`, {
    method: 'DELETE',
  })
}

export async function archiveWorkflow(slug: string, workflowId: string): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}/archive`, {
    method: 'POST',
  })
}

export async function restoreWorkflow(slug: string, workflowId: string): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}/restore`, {
    method: 'POST',
  })
}

export async function startWorkflow(slug: string, workflowId: string): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}/start`, {
    method: 'POST',
  })
}

export async function pauseWorkflow(slug: string, workflowId: string): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}/pause`, {
    method: 'POST',
  })
}

export async function stopWorkflow(slug: string, workflowId: string): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}/stop`, {
    method: 'POST',
  })
}

export async function runSpecificStep(
  slug: string,
  workflowId: string,
  stepNumber: number
): Promise<Workflow> {
  return request<Workflow>(
    `/projects/${slug}/workflows/${workflowId}/run-specific-step/${stepNumber}`,
    {
      method: 'POST',
    }
  )
}

export async function advanceWorkflowStep(
  slug: string,
  workflowId: string,
  options?: { skip_current?: boolean; artifacts?: Record<string, unknown> }
): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}/advance`, {
    method: 'POST',
    body: JSON.stringify(options || {}),
  })
}

// Step CRUD operations
export async function createWorkflowStep(
  slug: string,
  workflowId: string,
  data: {
    name: string
    step_type: 'interactive' | 'autonomous'
    description?: string
    loop_type?: string
    skippable?: boolean
    model?: 'sonnet' | 'opus' | 'haiku' | 'sonnet-1m'
    timeout?: number
    allowed_tools?: string[]
    // Loop limits (autonomous steps only)
    max_iterations?: number
    cooldown_between_iterations?: number
    max_consecutive_errors?: number
  }
): Promise<WorkflowStep> {
  return request<WorkflowStep>(`/projects/${slug}/workflows/${workflowId}/steps`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function updateWorkflowStep(
  slug: string,
  workflowId: string,
  stepId: number,
  data: {
    name?: string
    step_type?: 'interactive' | 'autonomous'
    description?: string
    loop_type?: string
    skippable?: boolean
    model?: 'sonnet' | 'opus' | 'haiku' | 'sonnet-1m'
    timeout?: number
    allowed_tools?: string[]
    // Loop limits (autonomous steps only)
    max_iterations?: number
    cooldown_between_iterations?: number
    max_consecutive_errors?: number
  }
): Promise<WorkflowStep> {
  return request<WorkflowStep>(`/projects/${slug}/workflows/${workflowId}/steps/${stepId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export async function archiveWorkflowStep(
  slug: string,
  workflowId: string,
  stepId: number
): Promise<WorkflowStep> {
  return request<WorkflowStep>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/archive`,
    { method: 'POST' }
  )
}

export async function restoreWorkflowStep(
  slug: string,
  workflowId: string,
  stepId: number
): Promise<WorkflowStep> {
  return request<WorkflowStep>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/restore`,
    { method: 'POST' }
  )
}

export async function listArchivedSteps(
  slug: string,
  workflowId: string
): Promise<WorkflowStep[]> {
  return request<WorkflowStep[]>(
    `/projects/${slug}/workflows/${workflowId}/steps/archived`
  )
}

export async function deleteWorkflowStep(
  slug: string,
  workflowId: string,
  stepId: number
): Promise<void> {
  return request<void>(`/projects/${slug}/workflows/${workflowId}/steps/${stepId}`, {
    method: 'DELETE',
  })
}

export async function reorderWorkflowSteps(
  slug: string,
  workflowId: string,
  stepIds: number[]
): Promise<Workflow> {
  return request<Workflow>(`/projects/${slug}/workflows/${workflowId}/steps/reorder`, {
    method: 'POST',
    body: JSON.stringify({ step_ids: stepIds }),
  })
}

// ============================================================================
// Planning Sessions API
// ============================================================================

export interface PlanningMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  metadata?: Record<string, unknown>
}

export interface PlanningSession {
  id: string
  workflow_id: string
  step_id: number
  messages: PlanningMessage[]
  artifacts?: {
    design_doc?: string
    guardrails?: string
  }
  status: 'active' | 'completed'
  created_at: string
  updated_at: string
}

export async function getPlanningSession(
  slug: string,
  workflowId: string
): Promise<PlanningSession> {
  return request<PlanningSession>(`/projects/${slug}/workflows/${workflowId}/planning`)
}

export async function sendPlanningMessage(
  slug: string,
  workflowId: string,
  content: string
): Promise<PlanningSession> {
  return request<PlanningSession>(`/projects/${slug}/workflows/${workflowId}/planning/message`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}

export async function updatePlanningArtifacts(
  slug: string,
  workflowId: string,
  artifacts: { design_doc?: string; guardrails?: string }
): Promise<PlanningSession> {
  return request<PlanningSession>(`/projects/${slug}/workflows/${workflowId}/planning/artifacts`, {
    method: 'PATCH',
    body: JSON.stringify(artifacts),
  })
}

export async function completePlanningSession(
  slug: string,
  workflowId: string,
  artifacts?: { design_doc?: string; guardrails?: string }
): Promise<PlanningSession> {
  return request<PlanningSession>(`/projects/${slug}/workflows/${workflowId}/planning/complete`, {
    method: 'POST',
    body: JSON.stringify(artifacts || {}),
  })
}

export function streamPlanningResponse(
  slug: string,
  workflowId: string
): EventSource {
  return new EventSource(`${API_BASE}/projects/${slug}/workflows/${workflowId}/planning/stream`)
}

export function streamPlanningArtifacts(
  slug: string,
  workflowId: string
): EventSource {
  return new EventSource(`${API_BASE}/projects/${slug}/workflows/${workflowId}/planning/generate-artifacts`)
}

// ============================================================================
// Workflow Resources API
// ============================================================================

export interface WorkflowResource {
  id: number
  workflow_id: string
  resource_type: string
  name: string
  content?: string
  file_path?: string
  source?: string
  source_id?: number
  enabled: boolean
  created_at: string
  updated_at: string
}

export async function listWorkflowResources(
  slug: string,
  workflowId: string,
  params?: { resource_type?: string; enabled?: boolean }
): Promise<WorkflowResource[]> {
  const searchParams = new URLSearchParams()
  if (params?.resource_type) searchParams.set('resource_type', params.resource_type)
  if (params?.enabled !== undefined) searchParams.set('enabled', params.enabled.toString())
  const query = searchParams.toString()
  return request<WorkflowResource[]>(
    `/projects/${slug}/workflows/${workflowId}/resources${query ? `?${query}` : ''}`
  )
}

export async function createWorkflowResource(
  slug: string,
  workflowId: string,
  data: {
    resource_type: string
    name: string
    content: string
    source?: string
  }
): Promise<WorkflowResource> {
  return request<WorkflowResource>(`/projects/${slug}/workflows/${workflowId}/resources`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getWorkflowResource(
  slug: string,
  workflowId: string,
  resourceId: number
): Promise<WorkflowResource> {
  return request<WorkflowResource>(
    `/projects/${slug}/workflows/${workflowId}/resources/${resourceId}`
  )
}

export async function updateWorkflowResource(
  slug: string,
  workflowId: string,
  resourceId: number,
  data: {
    name?: string
    content?: string
    enabled?: boolean
    expected_updated_at?: string  // For optimistic locking
  }
): Promise<WorkflowResource> {
  return request<WorkflowResource>(
    `/projects/${slug}/workflows/${workflowId}/resources/${resourceId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(data),
    }
  )
}

export async function deleteWorkflowResource(
  slug: string,
  workflowId: string,
  resourceId: number
): Promise<void> {
  return request<void>(
    `/projects/${slug}/workflows/${workflowId}/resources/${resourceId}`,
    { method: 'DELETE' }
  )
}

// ============================================================================
// Resource Versioning API
// ============================================================================

export interface ResourceVersion {
  id: number
  workflow_resource_id: number
  version_number: number
  content?: string
  name?: string
  created_at: string
}

export interface VersionListResponse {
  versions: ResourceVersion[]
  total: number
  limit: number
  offset: number
}

export async function listResourceVersions(
  slug: string,
  workflowId: string,
  resourceId: number,
  params?: { limit?: number; offset?: number }
): Promise<VersionListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.limit) searchParams.set('limit', params.limit.toString())
  if (params?.offset) searchParams.set('offset', params.offset.toString())
  const query = searchParams.toString()
  return request<VersionListResponse>(
    `/projects/${slug}/workflows/${workflowId}/resources/${resourceId}/versions${query ? `?${query}` : ''}`
  )
}

export async function restoreResourceVersion(
  slug: string,
  workflowId: string,
  resourceId: number,
  versionId: number
): Promise<WorkflowResource> {
  return request<WorkflowResource>(
    `/projects/${slug}/workflows/${workflowId}/resources/${resourceId}/versions/${versionId}/restore`,
    { method: 'POST' }
  )
}

export async function importProjectResourceToWorkflow(
  slug: string,
  workflowId: string,
  projectResourceId: number
): Promise<WorkflowResource> {
  return request<WorkflowResource>(
    `/projects/${slug}/workflows/${workflowId}/resources/import/${projectResourceId}`,
    { method: 'POST' }
  )
}

// ============================================================================
// Step Resources API (Per-Step Resource Overrides)
// ============================================================================

export interface StepResource {
  id: number
  step_id: number
  workflow_resource_id?: number
  resource_type?: string
  name?: string
  content?: string
  file_path?: string
  mode: 'override' | 'disable' | 'add'
  enabled: boolean
  priority: number
  created_at: string
  updated_at: string
}

export interface EffectiveResource {
  id: number
  resource_type: string
  name: string
  content?: string
  file_path?: string
  source: 'workflow' | 'step_override' | 'step_add'
  priority?: number
}

export interface PromptSection {
  position: string
  content: string
  resource_name?: string
  resource_type?: string
}

export interface PreviewPromptResponse {
  prompt_sections: PromptSection[]
  resources_used: string[]
  total_chars: number
  total_tokens_estimate: number
}

export async function listStepResources(
  slug: string,
  workflowId: string,
  stepId: number
): Promise<StepResource[]> {
  return request<StepResource[]>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/resources`
  )
}

export async function getEffectiveStepResources(
  slug: string,
  workflowId: string,
  stepId: number
): Promise<EffectiveResource[]> {
  return request<EffectiveResource[]>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/resources/effective`
  )
}

export async function createStepResource(
  slug: string,
  workflowId: string,
  stepId: number,
  data: {
    mode: 'override' | 'disable' | 'add'
    workflow_resource_id?: number
    resource_type?: string
    name?: string
    content?: string
    file_path?: string
    enabled?: boolean
    priority?: number
  }
): Promise<StepResource> {
  return request<StepResource>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/resources`,
    {
      method: 'POST',
      body: JSON.stringify(data),
    }
  )
}

export async function updateStepResource(
  slug: string,
  workflowId: string,
  stepId: number,
  resourceId: number,
  data: {
    name?: string
    content?: string
    file_path?: string
    enabled?: boolean
    priority?: number
  }
): Promise<StepResource> {
  return request<StepResource>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/resources/${resourceId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(data),
    }
  )
}

export async function deleteStepResource(
  slug: string,
  workflowId: string,
  stepId: number,
  resourceId: number
): Promise<void> {
  return request<void>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/resources/${resourceId}`,
    { method: 'DELETE' }
  )
}

export async function disableInheritedResource(
  slug: string,
  workflowId: string,
  stepId: number,
  workflowResourceId: number
): Promise<StepResource> {
  return request<StepResource>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/resources/disable/${workflowResourceId}`,
    { method: 'POST' }
  )
}

export async function enableInheritedResource(
  slug: string,
  workflowId: string,
  stepId: number,
  workflowResourceId: number
): Promise<void> {
  return request<void>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/resources/disable/${workflowResourceId}`,
    { method: 'DELETE' }
  )
}

export async function previewStepPrompt(
  slug: string,
  workflowId: string,
  stepId: number
): Promise<PreviewPromptResponse> {
  return request<PreviewPromptResponse>(
    `/projects/${slug}/workflows/${workflowId}/steps/${stepId}/preview-prompt`
  )
}

// ============================================================================
// Project Resources (Shared Library) API
// ============================================================================

export interface ProjectResource {
  id: number
  resource_type: string
  name: string
  content?: string
  description?: string
  auto_inherit: boolean
  created_at: string
  updated_at: string
}

export async function listProjectResources(
  slug: string,
  params?: { resource_type?: string }
): Promise<ProjectResource[]> {
  const searchParams = new URLSearchParams()
  if (params?.resource_type) searchParams.set('resource_type', params.resource_type)
  const query = searchParams.toString()
  return request<ProjectResource[]>(
    `/projects/${slug}/project-resources${query ? `?${query}` : ''}`
  )
}

export async function createProjectResource(
  slug: string,
  data: {
    resource_type: string
    name: string
    content: string
    description?: string
    auto_inherit?: boolean
  }
): Promise<ProjectResource> {
  return request<ProjectResource>(`/projects/${slug}/project-resources`, {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function getProjectResource(
  slug: string,
  resourceId: number
): Promise<ProjectResource> {
  return request<ProjectResource>(
    `/projects/${slug}/project-resources/${resourceId}`
  )
}

export async function updateProjectResource(
  slug: string,
  resourceId: number,
  data: {
    name?: string
    content?: string
    description?: string
    auto_inherit?: boolean
  }
): Promise<ProjectResource> {
  return request<ProjectResource>(
    `/projects/${slug}/project-resources/${resourceId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(data),
    }
  )
}

export async function deleteProjectResource(
  slug: string,
  resourceId: number
): Promise<void> {
  return request<void>(
    `/projects/${slug}/project-resources/${resourceId}`,
    { method: 'DELETE' }
  )
}

// ============================================================================
// Project Settings API
// ============================================================================

export interface ProjectSettings {
  id: number
  auto_inherit_guardrails: boolean
  require_design_doc: boolean
  architecture_first_mode: boolean
  updated_at: string | null
}

export async function getProjectSettings(slug: string): Promise<ProjectSettings> {
  return request<ProjectSettings>(`/projects/${slug}/settings`)
}

export async function updateProjectSettings(
  slug: string,
  data: {
    auto_inherit_guardrails?: boolean
    require_design_doc?: boolean
    architecture_first_mode?: boolean
  }
): Promise<ProjectSettings> {
  return request<ProjectSettings>(`/projects/${slug}/settings`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

// ============================================================================
// JSONL Import API
// ============================================================================

export interface ImportFormat {
  id: string
  label: string
  description?: string
  field_mapping: Record<string, string>
  sample_content?: string
}

export interface ImportJsonlResponse {
  imported: number
  skipped: number
  errors: string[]
  total_lines: number
}

export async function listImportFormats(slug: string): Promise<ImportFormat[]> {
  return request<ImportFormat[]>(`/projects/${slug}/import-formats`)
}

export async function importJsonlToWorkflow(
  slug: string,
  workflowId: string,
  sourceStepId: number,
  formatId: string,
  file: File,
  loopName?: string
): Promise<ImportJsonlResponse> {
  const formData = new FormData()
  formData.append('file', file)

  const params = new URLSearchParams({
    format_id: formatId,
    workflow_id: workflowId,
    source_step_id: sourceStepId.toString(),
  })
  if (loopName) params.set('loop_name', loopName)

  const response = await fetch(
    `${API_BASE}/projects/${slug}/import-jsonl?${params}`,
    {
      method: 'POST',
      body: formData,
    }
  )

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    const message = errorData.error?.message || errorData.detail || response.statusText
    throw new APIError(message, response.status, errorData.error?.code)
  }

  return response.json()
}

// ============================================================================
// Status Display Helpers
// ============================================================================

/**
 * Get user-friendly display name for work item status.
 * Internal status values are preserved for backend compatibility.
 */
export function getStatusDisplayName(status: string): string {
  const names: Record<string, string> = {
    pending: 'Queued',
    completed: 'Ready',
    claimed: 'In Progress',
    in_progress: 'In Progress',
    processed: 'Done',
    failed: 'Failed',
    skipped: 'Skipped',
    duplicate: 'Duplicate',
    external: 'External',
    rejected: 'Rejected',
  }
  return names[status] || status.charAt(0).toUpperCase() + status.slice(1)
}

/**
 * Get Tailwind CSS classes for status badge styling.
 */
export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    pending: 'bg-blue-500/20 text-blue-400',       // Queued - blue
    completed: 'bg-cyan-500/20 text-cyan-400',     // Ready - cyan
    claimed: 'bg-yellow-500/20 text-yellow-400',   // In Progress - yellow
    in_progress: 'bg-yellow-500/20 text-yellow-400',
    processed: 'bg-green-500/20 text-green-400',   // Done - green
    failed: 'bg-red-500/20 text-red-400',
    skipped: 'bg-gray-500/20 text-gray-400',
    duplicate: 'bg-orange-500/20 text-orange-400',
    external: 'bg-purple-500/20 text-purple-400',
    rejected: 'bg-red-500/20 text-red-400',
  }
  return colors[status] || 'bg-gray-500/20 text-gray-400'
}

export { APIError }
