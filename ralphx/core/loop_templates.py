"""Loop templates for RalphX.

Pre-built loop configurations for common use cases:
- planning: Generate user stories from design documents
- implementation: Implement stories with Phase 1 grouping
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import yaml


def generate_loop_id(loop_type: str, existing_names: list[str] | None = None) -> str:
    """Generate a unique loop ID with daily counter.

    Format: {type}-{YYYYMMDD}_{n}
    Example: planning-20260115_1, implementation-20260115_2

    The counter `n` starts at 1 for each day and auto-increments
    if a loop with that ID already exists.

    Args:
        loop_type: The type of loop (planning, implementation, etc.)
        existing_names: List of existing loop names to check for collisions.

    Returns:
        Unique loop identifier string.
    """
    today = datetime.now().strftime("%Y%m%d")
    prefix = f"{loop_type}-{today}_"

    if not existing_names:
        return f"{prefix}1"

    # Find all existing loops with this prefix and extract their counters
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    existing_counters = []

    for name in existing_names:
        match = pattern.match(name)
        if match:
            existing_counters.append(int(match.group(1)))

    # Find the next available counter
    if not existing_counters:
        return f"{prefix}1"

    next_counter = max(existing_counters) + 1
    return f"{prefix}{next_counter}"


# ============================================================================
# Planning Loop Template
# ============================================================================

PLANNING_LOOP_CONFIG = """
name: planning
display_name: "Planning Loop"
type: generator
description: "Generate user stories from design documents and requirements"

item_types:
  output:
    singular: story
    plural: stories
    description: "User stories extracted from design documents"

modes:
  extract:
    description: "Extract stories from design documents"
    model: sonnet
    timeout: 300
    tools: []
    prompt_template: prompts/extract.md

  research:
    description: "Research best practices via web search"
    model: sonnet
    timeout: 600
    tools: [WebSearch, WebFetch]
    prompt_template: prompts/research.md

mode_selection:
  strategy: weighted_random
  weights:
    extract: 80
    research: 20

context:
  inputs_dir: inputs/

limits:
  max_iterations: 100
  max_consecutive_errors: 5
  cooldown_between_iterations: 3
"""

PLANNING_EXTRACT_PROMPT = """# Story Extraction Mode

You are analyzing design documents to extract user stories for implementation.

## Existing Stories (DO NOT DUPLICATE)

Total stories generated so far: {{total_stories}}

### Previously Generated Stories
Reference these IDs when specifying dependencies:
{{existing_stories}}

### Category Statistics
Use these to assign the next available ID for each category:
{{category_stats}}

## Input Documents

The following documents are available in the inputs directory:
{{inputs_list}}

## Your Task

1. Read through the design documents carefully
2. Generate NEW stories (do not duplicate existing ones above)
3. For each story, provide:
   - **ID**: Use format CATEGORY-NNN (see category stats for next number)
   - A clear title
   - User story format: "As a [user], I want [feature] so that [benefit]"
   - Acceptance criteria (testable conditions)
   - Priority (1-5, where 1 is highest)
   - Category (uppercase: AUTH, API, DB, UI, INFRA, etc.)
   - Estimated complexity (small, medium, large)
   - **Dependencies**: Array of story IDs this depends on

## Output Format

Return your findings as JSON:
```json
{
  "stories": [
    {
      "id": "AUTH-043",
      "title": "Short descriptive title",
      "content": "As a user, I want to...",
      "acceptance_criteria": ["Criterion 1", "Criterion 2"],
      "priority": 1,
      "category": "AUTH",
      "complexity": "medium",
      "dependencies": ["AUTH-001", "AUTH-002"]
    }
  ],
  "notes": "Any observations about the documents"
}
```

## ID Assignment Rules

1. Look at category_stats to find the next available ID for each category
2. If category "AUTH" has next_id: 43, use "AUTH-043" for your first AUTH story
3. If you generate multiple stories in the same category, increment: AUTH-043, AUTH-044, etc.
4. For new categories not in category_stats, start at 001

## Dependency Guidelines

- **Infrastructure/foundation stories** typically have NO dependencies (they are the foundation)
- **Feature stories** depend on their infrastructure (e.g., "AUTH-005" depends on "AUTH-001" if AUTH-001 creates the user model)
- **UI stories** depend on their backend (e.g., "UI-003" depends on "API-002" for the endpoint it calls)
- **ONLY reference story IDs** that:
  1. Exist in "Previously Generated Stories" above, OR
  2. Are other stories in THIS batch you're generating
- If a dependency hasn't been created yet, note it in acceptance_criteria instead

## Guidelines

- Each story should be independently implementable (given its dependencies)
- Break large features into smaller stories
- Avoid duplicating stories that already exist
- Flag any ambiguous requirements for clarification
- Mark infrastructure/architecture stories with category "INFRA" or "ARCH"
"""

PLANNING_RESEARCH_PROMPT = """# Research Mode

You are researching best practices and implementation approaches for the project.

## Context

Based on the design documents in the inputs directory, research relevant:
- Industry best practices
- Common implementation patterns
- Security considerations
- Performance optimizations

## Your Task

1. Identify areas where research would be valuable
2. Search for relevant information
3. Synthesize findings into actionable recommendations

## Output Format

Return your findings as JSON:
```json
{
  "topic": "What you researched",
  "findings": [
    {
      "insight": "Key finding",
      "source": "Where you found it",
      "applicability": "How it applies to our project"
    }
  ],
  "recommendations": [
    "Specific recommendation for implementation"
  ],
  "additional_stories": [
    {
      "id": "STORY-RES-001",
      "title": "Story suggested by research",
      "content": "As a user, I want...",
      "rationale": "Why this story was identified through research"
    }
  ]
}
```
"""


# ============================================================================
# Implementation Loop Template
# ============================================================================

IMPLEMENTATION_LOOP_CONFIG = """
name: implementation
display_name: "Implementation Loop"
type: consumer
description: "Implement user stories with Phase 1 architecture grouping"

item_types:
  input:
    singular: story
    plural: stories
    source: planning
    description: "User stories to implement"
  output:
    singular: implementation
    plural: implementations
    description: "Completed implementation records"

modes:
  phase1_analyze:
    description: "Analyze all stories for Phase 1 grouping"
    model: sonnet
    timeout: 600
    tools: []
    prompt_template: prompts/phase1-analyze.md
    phase: phase_1

  phase1_implement:
    description: "Implement Phase 1 architecture stories as batch"
    model: sonnet
    timeout: 3600
    tools: [Read, Write, Edit, Bash, Glob, Grep]
    prompt_template: prompts/phase1-implement.md
    phase: phase_1

  implement:
    description: "Implement a single story"
    model: sonnet
    timeout: 1800
    tools: [Read, Write, Edit, Bash, Glob, Grep]
    prompt_template: prompts/implement.md

mode_selection:
  strategy: phase_aware
  fixed_mode: implement

phase_config:
  enabled: true
  auto_group: true
  max_phase1_items: 10
  phase1_categories:
    - architecture
    - infrastructure
    - setup
    - foundation
    - database
    - auth

context:
  inputs_dir: inputs/

limits:
  max_iterations: 50
  max_consecutive_errors: 3
  cooldown_between_iterations: 5
"""

IMPLEMENTATION_PHASE1_ANALYZE_PROMPT = """# Phase 1 Analysis Mode

You are analyzing all pending stories to identify which ones should be implemented
together in Phase 1 (architecture/infrastructure foundation).

## All Pending Stories

{{stories_json}}

## Your Task

1. Review ALL stories above
2. Identify stories that are:
   - Architecture or infrastructure setup
   - Foundation that other stories depend on
   - Database schema or models
   - Authentication/authorization setup
   - Core API routing or middleware
   - Shared utilities that multiple stories need

3. Group these stories for batch implementation
4. Determine the optimal implementation order within Phase 1

## Output Format

Return your analysis as JSON:
```json
{
  "phase_1_group": ["STORY-001", "STORY-005", "STORY-012"],
  "reasoning": {
    "STORY-001": "Sets up database schema - all other stories depend on this",
    "STORY-005": "Creates auth middleware - required before protected routes",
    "STORY-012": "Establishes API routing structure"
  },
  "implementation_order": ["STORY-012", "STORY-001", "STORY-005"],
  "dependencies": {
    "STORY-001": [],
    "STORY-005": ["STORY-001"],
    "STORY-012": []
  },
  "excluded_reasoning": {
    "STORY-002": "Feature-specific, not infrastructure"
  }
}
```

## Guidelines

- Include 3-10 stories maximum in Phase 1
- Only include true infrastructure/architecture stories
- Consider what OTHER stories will need as foundation
- The implementation order should respect dependencies
"""

IMPLEMENTATION_PHASE1_IMPLEMENT_PROMPT = """# Phase 1 Implementation Mode

You are implementing the Phase 1 architecture/infrastructure stories as a batch.

## Stories to Implement

{{phase1_stories_json}}

## Implementation Order

{{implementation_order}}

## Architecture Guidance

{{architecture_context}}

## Your Task

Implement ALL Phase 1 stories in the specified order. For each story:

1. Read existing code to understand the codebase structure
2. Implement the story according to its acceptance criteria
3. Write tests where appropriate
4. Ensure code follows project conventions

## Important

- These are FOUNDATION stories - they should establish patterns for later stories
- Create clear abstractions that other stories can build on
- Document any architectural decisions
- Run tests after implementation

## Output Format

After completing implementation, return a summary as JSON:
```json
{
  "completed_stories": ["STORY-001", "STORY-005", "STORY-012"],
  "files_created": ["path/to/file1.py", "path/to/file2.py"],
  "files_modified": ["path/to/existing.py"],
  "tests_added": ["test_file.py"],
  "architectural_decisions": [
    "Decision 1 and rationale",
    "Decision 2 and rationale"
  ],
  "notes_for_next_stories": "Any context that will help implement remaining stories"
}
```
"""

IMPLEMENTATION_IMPLEMENT_PROMPT = """# Story Implementation Mode

You are implementing a single user story.

## Story to Implement

{{story_json}}

## Architecture Context

{{architecture_context}}

## Phase 1 Foundation

The following infrastructure is already in place:
{{phase1_summary}}

## Your Task

1. Read the story and its acceptance criteria carefully
2. Review relevant existing code
3. Implement the story
4. Write tests for the implementation
5. Verify acceptance criteria are met

## Guidelines

- Build on existing patterns from Phase 1
- Follow project code conventions
- Keep changes focused on this story
- Run relevant tests to verify

## Output Format

After completing implementation, return a summary as JSON:
```json
{
  "story_id": "STORY-XXX",
  "status": "completed",
  "files_created": [],
  "files_modified": [],
  "tests_added": [],
  "acceptance_criteria_met": {
    "criterion_1": true,
    "criterion_2": true
  },
  "notes": "Any relevant observations"
}
```
"""


# ============================================================================
# Template Registry
# ============================================================================

LOOP_TEMPLATES = {
    "planning": {
        "name": "Planning Loop",
        "description": "Generate user stories from design documents",
        "config": PLANNING_LOOP_CONFIG,
        "prompts": {
            "extract.md": PLANNING_EXTRACT_PROMPT,
            "research.md": PLANNING_RESEARCH_PROMPT,
        },
        "permission_template": "planning",
    },
    "implementation": {
        "name": "Implementation Loop",
        "description": "Implement stories with Phase 1 architecture grouping",
        "config": IMPLEMENTATION_LOOP_CONFIG,
        "prompts": {
            "phase1-analyze.md": IMPLEMENTATION_PHASE1_ANALYZE_PROMPT,
            "phase1-implement.md": IMPLEMENTATION_PHASE1_IMPLEMENT_PROMPT,
            "implement.md": IMPLEMENTATION_IMPLEMENT_PROMPT,
        },
        "permission_template": "implementation",
    },
}


def list_loop_templates() -> list[dict]:
    """List all available loop templates.

    Returns:
        List of template info dicts with id, name, and description.
    """
    return [
        {
            "id": template_id,
            "name": template["name"],
            "description": template["description"],
        }
        for template_id, template in LOOP_TEMPLATES.items()
    ]


def get_loop_template(template_id: str) -> Optional[dict]:
    """Get a loop template by ID.

    Args:
        template_id: Template identifier (e.g., 'planning', 'implementation').

    Returns:
        Template dict with config, prompts, and permission_template, or None.
    """
    return LOOP_TEMPLATES.get(template_id)


def create_loop_from_template(
    project_path: Path,
    loop_name: str,
    template_id: str,
    custom_name: Optional[str] = None,
) -> Path:
    """Create a new loop from a template.

    Creates the loop directory structure with config and prompts.

    Args:
        project_path: Path to the project directory.
        loop_name: Name for the new loop (used as directory name).
        template_id: Template to use ('planning', 'implementation').
        custom_name: Optional custom display name.

    Returns:
        Path to the created loop directory.

    Raises:
        ValueError: If template_id is invalid.
        FileExistsError: If loop already exists.
    """
    from ralphx.core.workspace import (
        ensure_loop_directory,
        get_loop_config_path,
        get_loop_prompts_path,
    )
    from ralphx.core.permission_templates import apply_template_to_loop

    template = LOOP_TEMPLATES.get(template_id)
    if not template:
        raise ValueError(f"Unknown loop template: {template_id}")

    # Ensure loop directory exists
    loop_dir = ensure_loop_directory(project_path, loop_name)

    # Parse and customize the config
    config_data = yaml.safe_load(template["config"])
    config_data["name"] = loop_name
    if custom_name:
        config_data["display_name"] = custom_name

    # Write loop config
    config_path = get_loop_config_path(project_path, loop_name)
    with open(config_path, "w") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

    # Write prompt templates
    prompts_dir = get_loop_prompts_path(project_path, loop_name)
    for prompt_name, prompt_content in template["prompts"].items():
        prompt_path = prompts_dir / prompt_name
        with open(prompt_path, "w") as f:
            f.write(prompt_content.strip())

    # Apply permission template
    if template.get("permission_template"):
        apply_template_to_loop(project_path, loop_name, template["permission_template"])

    return loop_dir


def get_template_config(template_id: str) -> Optional[str]:
    """Get just the YAML config for a template.

    Args:
        template_id: Template identifier.

    Returns:
        YAML config string, or None if not found.
    """
    template = LOOP_TEMPLATES.get(template_id)
    if template:
        return template["config"]
    return None


def get_template_prompts(template_id: str) -> Optional[dict[str, str]]:
    """Get the prompt templates for a loop template.

    Args:
        template_id: Template identifier.

    Returns:
        Dict mapping prompt filename to content, or None if not found.
    """
    template = LOOP_TEMPLATES.get(template_id)
    if template:
        return template["prompts"]
    return None


# ============================================================================
# Simple Loop Creation Helpers
# ============================================================================

def generate_simple_planning_config(
    name: str,
    display_name: str = "Planning",
    description: str = "",
) -> str:
    """Generate YAML config for a simple planning loop.

    Args:
        name: Unique loop ID (auto-generated, e.g., planning-20260115_1).
        display_name: User-facing name (can be duplicated across loops).
        description: Optional user-provided description.

    Returns:
        YAML configuration string.
    """
    desc_line = description if description else "Generate user stories from design documents"

    return f"""name: {name}
display_name: "{display_name}"
type: generator
description: "{desc_line}"

item_types:
  output:
    singular: story
    plural: stories
    description: User stories for implementation

modes:
  default:
    description: Extract and generate user stories
    model: sonnet
    timeout: 300
    prompt_template: .ralphx/loops/{name}/prompts/planning.md
    tools: []

mode_selection:
  strategy: fixed
  fixed_mode: default

context:
  inputs_dir: inputs/

limits:
  max_iterations: 100
  max_runtime_seconds: 28800
  max_consecutive_errors: 5
  cooldown_between_iterations: 5
"""


def generate_simple_implementation_config(
    name: str,
    source_loop: Optional[str] = None,
    display_name: str = "Implementation",
    description: str = "",
) -> str:
    """Generate YAML config for a simple implementation loop.

    Args:
        name: Unique loop ID (auto-generated, e.g., implementation-20260115_1).
        source_loop: Name of planning loop to consume stories from.
        display_name: User-facing name (can be duplicated across loops).
        description: Optional user-provided description.

    Returns:
        YAML configuration string.
    """
    source_section = f"    source: {source_loop}" if source_loop else ""
    desc_line = description if description else "Implement user stories as working code"

    return f"""name: {name}
display_name: "{display_name}"
type: consumer
description: "{desc_line}"

item_types:
  input:
    singular: story
    plural: stories
{source_section}
    description: Stories to implement
  output:
    singular: implementation
    plural: implementations
    description: Completed implementations

modes:
  default:
    description: Implement a user story
    model: sonnet
    timeout: 1800
    prompt_template: .ralphx/loops/{name}/prompts/implement.md
    tools:
      - Read
      - Write
      - Edit
      - Bash
      - Glob
      - Grep

mode_selection:
  strategy: fixed
  fixed_mode: default

context:
  inputs_dir: inputs/

limits:
  max_iterations: 50
  max_runtime_seconds: 28800
  max_consecutive_errors: 3
  cooldown_between_iterations: 5
"""
