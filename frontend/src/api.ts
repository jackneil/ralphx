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
  source_loop: string | null
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
  project_id: string
  content: string
  title?: string
  status: string
  category?: string
  priority?: number
  source_loop?: string
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
}

export async function listItems(
  slug: string,
  params?: {
    status?: string
    category?: string
    source_loop?: string
    limit?: number
    offset?: number
  }
) {
  const searchParams = new URLSearchParams()
  if (params?.status) searchParams.set('status', params.status)
  if (params?.category) searchParams.set('category', params.category)
  if (params?.source_loop) searchParams.set('source_loop', params.source_loop)
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
    category?: string
    priority?: number
    metadata?: Record<string, unknown>
  }
) {
  return request<{
    id: string
    content: string
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
    status?: string
    category?: string
    priority?: number
    metadata?: Record<string, unknown>
  }
) {
  return request<{
    id: string
    content: string
    status: string
    updated_at: string
  }>(`/projects/${slug}/items/${itemId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
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
  return request<PermissionTemplateInfo[]>('/permission-templates')
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

export { APIError }
