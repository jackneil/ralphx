# Loop Configuration Schema

This document defines the YAML schema for loop configurations in RalphX.

## Complete Schema

```yaml
# Required: Unique identifier for the loop
name: string  # lowercase, alphanumeric + underscores

# Required: Human-readable name
display_name: string

# Optional: Description of what this loop does
description: string

# Required: Loop type
type: generator | consumer | hybrid

# Required: Execution modes
modes:
  <mode_name>:  # e.g., "turbo", "deep", "review"
    description: string
    timeout: integer  # seconds
    model: string     # sonnet | opus | haiku | gpt-4 | etc.
    tools: string[]   # WebSearch, WebFetch, Read, Write, Bash, etc.
    prompt_template: string  # path to .md file or inline template

    # Optional: Mode-specific guardrail overrides (highest precedence)
    guardrails:
      categories:
        domain: boolean           # e.g., false to skip domain rules in turbo mode
      include:
        - string                  # Additional files for this mode
      exclude:
        - string                  # Files to skip for this mode

# Required: How modes are selected each iteration
mode_selection:
  strategy: fixed | random | weighted_random | adaptive
  fixed_mode: string        # Required if strategy=fixed
  weights:                  # Required if strategy=weighted_random
    <mode_name>: integer    # Percentage (should sum to 100)

# Optional: Category configuration (for organized work items)
categories:
  source: file | inline | none
  file: string              # Path to categories.yaml
  inline:                   # Inline category definitions
    <prefix>:
      name: string
      description: string
      color: string         # Hex color for UI
  selection:
    strategy: random | weighted | sequential | forced
    forced_category: string # Required if strategy=forced
    weight_by: count | priority | age

# Optional: Phase configuration (for ordered execution)
phases:
  source: file | inline | none
  file: string              # Path to phases.yaml
  inline:
    <phase_number>:
      name: string
      categories: string[]
      depends_on: integer[] # Phase numbers this depends on

# Required: Output configuration
output:
  format: sqlite            # SQLite is the only storage backend (see DESIGN.md Section 10)
  # Note: jsonl and api formats were considered but SQLite provides better
  # atomic transactions, indexing, and single-file backup

  # Schema for work items
  schema:
    required:
      - id
      - priority
      - content
      - status
    optional:
      - category
      - tags
      - metadata
      - depends_on
      - acceptance_criteria

    # Custom field definitions
    custom_fields:
      <field_name>:
        type: string | integer | boolean | array | object
        required: boolean
        default: any

# Optional: Context configuration
context:
  design_doc: string              # Path to design document (relative to project)
  custom_context:                 # Additional context variables
    <var_name>: string            # Available in prompt templates as {var_name}

  # Guardrails configuration (see DESIGN.md Section 9 for full details)
  guardrails:
    enabled: boolean              # Enable/disable guardrails (default: true)
    inherit_global: boolean       # Include ~/.ralphx/guardrails/ (default: true)

    # Enable/disable specific categories
    categories:
      system: boolean             # Before design_doc (default: true)
      safety: boolean             # At start of prompt (default: true)
      domain: boolean             # After design_doc (default: true)
      output: boolean             # At end of prompt (default: true)
      custom: boolean             # After design_doc (default: true)

    # Explicit file include/exclude (relative to guardrails dir)
    include:
      - string                    # e.g., "safety/hipaa.md"
    exclude:
      - string                    # e.g., "output/verbose.md"

    # Additional guardrails (inline or file reference)
    # Each item is EITHER a file reference OR inline content (not both)
    additional:
      - file: string              # Path to additional guardrail file
      # OR
      - content: |                # Inline guardrail content
          ## Inline Rule
          Focus on user stories only.
      # Example with multiple items:
      # additional:
      #   - file: "extra/special-rules.md"
      #   - content: "Always use TypeScript"
      #   - file: "compliance/soc2.md"

# Required: Execution limits
limits:
  max_iterations: integer           # 0 = unlimited
  max_runtime_seconds: integer      # 0 = unlimited
  max_consecutive_errors: integer   # Abort threshold
  max_no_progress_iterations: integer
  cooldown_between_iterations: integer  # Seconds to wait

# Optional: Execution behavior
execution:
  permission_mode: default | auto-approve | fail-fast
  # default: Claude asks for permission (may block unattended loops)
  # auto-approve: Skip all permission prompts (use with caution!)
  # fail-fast: Fail immediately if permission would be required

  permission_timeout: integer     # Seconds to wait before treating as stuck (default: 30)
  on_permission_block: skip | retry | abort | notify
  # skip: Skip this iteration, continue loop
  # retry: Retry after timeout
  # abort: Stop the loop
  # notify: Alert user but keep waiting

  activity_timeout:               # Mode-aware silence detection
    warn: integer                 # Seconds of silence before warning (default: varies by mode)
    kill: integer                 # Seconds of silence before killing (default: varies by mode)
    # turbo mode defaults: warn=45, kill=180
    # deep mode defaults: warn=120, kill=600

# Optional: Error handling
error_handling:
  on_timeout: retry | skip | abort
  max_retries: integer
  retry_delay: integer              # Seconds
  on_parse_error: skip | abort
  on_api_error: retry | skip | abort

# Optional: Hooks for lifecycle events
# SECURITY WARNING: Shell hooks execute arbitrary commands. RalphX sanitizes
# template variables ({iteration}, {item_id}, etc.) to prevent shell injection:
# - Variables are quoted and shell metacharacters are escaped
# - Only alphanumeric characters, hyphens, underscores, and periods are allowed
# - Variables exceeding 1000 characters are truncated
# Consider using webhook hooks for untrusted environments.
hooks:
  on_start:
    - type: shell | webhook | log
      command: string               # For shell (variables are sanitized)
      url: string                   # For webhook
      message: string               # For log

  on_iteration_complete:
    - type: shell | webhook | log
      command: string

  on_item_added:
    - type: shell | webhook | log
      command: string

  on_complete:
    - type: shell | webhook | log
      command: string

  on_error:
    - type: shell | webhook | log
      command: string

# Optional: Git integration
git:
  enabled: boolean
  auto_commit: boolean
  commit_template: string           # Supports {loop_name}, {count}, {mode}, {category}
  branch: string                    # Branch to commit to

# Optional: Credentials/auth
auth:
  adapter: default | file | env
  credentials_file: string          # For file adapter
  env_var: string                   # For env adapter

# Optional: Logging
logging:
  level: debug | info | warning | error
  file: string                      # Log file path
  max_size_mb: integer              # Log rotation size
  keep_files: integer               # Number of old logs to keep
  verbose: boolean                  # Show detailed output (prompts, responses)
  debug_dir: string                 # Directory for debug dumps (prompts, responses)
```

## Minimal Example

```yaml
name: simple_research
display_name: "Simple Research"
type: generator

modes:
  default:
    timeout: 300
    model: sonnet
    tools: []
    prompt_template: prompts/research.md

mode_selection:
  strategy: fixed
  fixed_mode: default

output:
  format: sqlite            # All data stored in ~/.ralphx/ralphx.db
  schema:
    required: [id, content, status]

limits:
  max_iterations: 10
  max_consecutive_errors: 3
```

## Full Example (Ralph-style PRD Research)

```yaml
name: prd_research
display_name: "PRD Research Loop"
description: "Discovers and generates user stories via design doc extraction and web research"
type: generator

modes:
  turbo:
    description: "Fast extraction from existing design documents"
    timeout: 180
    model: sonnet
    tools: []
    prompt_template: prompts/turbo.md
    guardrails:
      categories:
        domain: false             # Skip domain rules in turbo mode for speed

  deep:
    description: "Thorough web research for industry best practices"
    timeout: 900
    model: sonnet
    tools: [WebSearch, WebFetch]
    prompt_template: prompts/deep.md
    guardrails:
      include:
        - "safety/web-research.md"  # Additional safety for web research

mode_selection:
  strategy: weighted_random
  weights:
    turbo: 85
    deep: 15

categories:
  source: file
  file: categories.yaml
  selection:
    strategy: weighted
    weight_by: count  # Favor under-represented categories

# Context for prompt templates
context:
  design_doc: design/DESIGN.md
  custom_context:
    domain: "Revenue Cycle Management"
    target_system: "Healthcare billing software"

  # Guardrails configuration
  guardrails:
    enabled: true
    inherit_global: true          # Include ~/.ralphx/guardrails/
    categories:
      system: true
      safety: true                # Include safety rules
      domain: true                # Include domain-specific rules
      output: true                # Include output format rules
    include:
      - "safety/hipaa.md"         # Explicitly include HIPAA rules
    exclude:
      - "output/verbose.md"       # Skip verbose output format

output:
  format: sqlite            # All data stored in ~/.ralphx/ralphx.db
  schema:
    required:
      - id
      - priority
      - story
      - acceptance_criteria
      - passes
    optional:
      - category
      - notes
      - tags

limits:
  max_iterations: 100
  max_runtime_seconds: 28800  # 8 hours
  max_consecutive_errors: 5
  max_no_progress_iterations: 3
  cooldown_between_iterations: 5

# Execution behavior (permission handling, activity detection)
execution:
  permission_mode: default        # default | auto-approve | fail-fast
  permission_timeout: 30          # Seconds before treating as stuck
  on_permission_block: skip       # skip | retry | abort | notify
  activity_timeout:
    warn: 45                      # Warn after 45s of silence (turbo mode)
    kill: 180                     # Kill after 180s of silence

error_handling:
  on_timeout: skip
  on_parse_error: skip
  max_retries: 2
  retry_delay: 10

hooks:
  on_iteration_complete:
    - type: log
      message: "Iteration {iteration} complete: +{items_added} items"

git:
  enabled: true
  auto_commit: true
  commit_template: "PRD: Add {count} stories from {mode} mode"

logging:
  level: info
  file: logs/prd_research.log
  max_size_mb: 10
  keep_files: 5
  verbose: false                  # Set true for detailed output
```

## Implementation Loop Example

```yaml
name: prd_implementation
display_name: "PRD Implementation Loop"
description: "Implements pending user stories from PRD"
type: consumer

modes:
  implement:
    description: "Full implementation with all tools"
    timeout: 1800  # 30 minutes per feature
    model: sonnet
    tools: [Read, Write, Edit, Bash, Glob, Grep]
    prompt_template: prompts/implement.md

mode_selection:
  strategy: fixed
  fixed_mode: implement

phases:
  source: file
  file: phases.yaml

output:
  format: sqlite            # Same SQLite database as research loop
  schema:
    required:
      - id
      - priority
      - story
      - acceptance_criteria
      - passes
    optional:
      - status
      - implemented_at
      - dup_of
      - external_product

limits:
  max_iterations: 50
  max_runtime_seconds: 28800
  max_consecutive_errors: 3

# Implementation needs longer activity timeouts
execution:
  permission_mode: default        # May need user approval for Bash commands
  permission_timeout: 60          # Allow more time for complex operations
  on_permission_block: notify     # Alert user rather than skip
  activity_timeout:
    warn: 120                     # Implementation takes longer
    kill: 600                     # 10 minute silence threshold

hooks:
  on_item_added:
    - type: shell
      command: "git add -A && git commit -m 'Implement {item_id}'"

git:
  enabled: true
  auto_commit: true
  commit_template: "Implement {item_id}: {item_summary}"
```

## Template Variables

Prompt templates support these variables:

### Always Available
- `{loop_name}` - Loop identifier
- `{iteration}` - Current iteration number
- `{mode}` - Current mode name
- `{timestamp}` - ISO timestamp

### Category Mode
- `{category}` - Selected category prefix
- `{category_name}` - Category display name
- `{category_description}` - Category description
- `{category_stories}` - Existing stories in category
- `{next_id}` - Next available ID for category

### Consumer Mode
- `{item_id}` - Current work item ID
- `{item_content}` - Work item content
- `{item_priority}` - Work item priority
- `{item_metadata}` - JSON of item metadata

### Custom
- `{design_doc}` - Contents of design document (if configured)
- `{implemented_summary}` - Summary of implemented items
- Any custom variables defined in loop config

### Guardrails Variable Support
Guardrail markdown files can also use template variables:
```markdown
<!-- guardrails/domain/healthcare.md -->
# {domain} Rules

You are building {target_system}. Follow these guidelines...
```

**Important**: If a guardrail uses an undefined variable, RalphX will error at load time (fail fast).
Validate with: `ralphx guardrails validate --project <slug>`
