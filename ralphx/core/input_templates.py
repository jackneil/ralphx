"""Input templates for loop inputs.

Pre-curated input files (instructions, guardrails) that users can apply to loops.
These are different from loop_templates which define loop configurations.

Input templates are:
- Loop-type specific (planning vs implementation)
- Tagged with their role (story_instructions, guardrails, reference, etc.)
- Can be previewed and applied to any loop of matching type
"""

from typing import Optional

# Input tag definitions
INPUT_TAGS = {
    "master_design": {
        "label": "Master Design",
        "description": "PRD, spec, or architecture document",
    },
    "story_instructions": {
        "label": "Story Instructions",
        "description": "How to generate stories from design documents",
    },
    "stories": {
        "label": "Stories (JSONL)",
        "description": "Stories to implement in JSONL format",
    },
    "guardrails": {
        "label": "Guardrails",
        "description": "Quality rules and constraints",
    },
    "reference": {
        "label": "Reference",
        "description": "Additional reference material",
    },
}

# Required tags by loop type
REQUIRED_TAGS_BY_LOOP_TYPE = {
    "planning": ["master_design", "story_instructions"],
    "implementation": ["master_design", "stories"],
}

# ============================================================================
# Planning Input Templates
# ============================================================================

STORY_INSTRUCTIONS_CONTENT = """# Story Generation Instructions

You are a senior technical product manager analyzing design documents to extract user stories.

## Your Role
- Read provided design documents thoroughly
- Extract discrete, implementable user stories
- Ensure each story is independent and testable
- Prioritize based on dependencies and value

## Output Format
For each story, provide:
1. **ID**: STORY-XXX (unique identifier)
2. **Title**: Brief descriptive title
3. **User Story**: "As a [user], I want [feature] so that [benefit]"
4. **Acceptance Criteria**: Testable conditions (at least 2)
5. **Priority**: 1-5 (1=highest)
6. **Category**: auth, ui, api, database, infrastructure
7. **Dependencies**: List of story IDs this depends on

## Guidelines
- Break large features into 1-3 day stories
- Infrastructure stories marked for Phase 1
- Flag ambiguous requirements for clarification
- Each story should be independently implementable
- Identify dependencies between stories
- Mark infrastructure/architecture stories appropriately

## JSON Output Structure
```json
{
  "stories": [
    {
      "id": "STORY-001",
      "title": "Short descriptive title",
      "content": "As a user, I want to...",
      "acceptance_criteria": ["Criterion 1", "Criterion 2"],
      "priority": 1,
      "category": "category-name",
      "complexity": "medium",
      "dependencies": []
    }
  ],
  "notes": "Any observations about the documents"
}
```
"""

STORY_GUARDRAILS_CONTENT = """# Story Quality Guardrails

## Required Fields
Every story MUST include:
- Unique ID in STORY-XXX format
- User story in proper format ("As a..., I want..., so that...")
- At least 2 acceptance criteria
- Valid priority (1-5)
- Category assignment

## Quality Rules

### Size
- Stories should be completable in 1-3 days
- If a story seems larger, break it down

### Dependencies
- No story should have more than 3 dependencies
- Dependencies must reference valid story IDs
- Avoid circular dependencies

### Categories
Infrastructure stories belong in:
- architecture
- infrastructure
- database
- auth

Feature stories belong in:
- ui
- api
- feature

### Acceptance Criteria
- Must be testable (yes/no determination)
- Should be specific, not vague
- Include edge cases where relevant

## Anti-Patterns to Avoid
- Stories that are just "implement X" without user value
- Acceptance criteria that are implementation details
- Dependencies on stories that don't exist
- Multiple unrelated changes in one story
"""

# ============================================================================
# Implementation Input Templates
# ============================================================================

IMPLEMENTATION_INSTRUCTIONS_CONTENT = """# Implementation Instructions

You are implementing user stories for a software project.

## Your Role
- Read each story and its acceptance criteria carefully
- Review relevant existing code before making changes
- Implement the story according to specifications
- Write tests for the implementation
- Ensure code follows project conventions

## Process
1. Understand the story requirements
2. Explore existing codebase for relevant patterns
3. Plan the implementation approach
4. Write the code
5. Add appropriate tests
6. Verify acceptance criteria are met

## Guidelines
- Build on existing patterns in the codebase
- Keep changes focused on the story scope
- Don't over-engineer - implement what's needed
- Handle error cases appropriately
- Add comments only where logic isn't self-evident

## Output Format
After completing implementation, provide a summary:
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

CODE_GUARDRAILS_CONTENT = """# Code Quality Guardrails

## Security Requirements
- Never hardcode secrets or credentials
- Validate all user inputs
- Use parameterized queries for database access
- Implement proper authentication checks
- Sanitize outputs to prevent XSS
- Follow principle of least privilege

## Code Style
- Follow existing project conventions
- Use meaningful variable and function names
- Keep functions focused and small
- Add type hints where the project uses them
- Match existing indentation and formatting

## Testing Requirements
- Write tests for new functionality
- Cover happy path and error cases
- Test edge cases and boundary conditions
- Ensure tests are deterministic

## Error Handling
- Handle errors at appropriate levels
- Provide meaningful error messages
- Don't swallow exceptions silently
- Log errors appropriately

## Performance
- Avoid N+1 query patterns
- Use appropriate data structures
- Consider caching for expensive operations
- Don't premature optimize

## Documentation
- Update README if adding new features
- Document complex algorithms
- Keep API documentation current
- Add comments for non-obvious logic only

## Anti-Patterns to Avoid
- God objects/functions that do everything
- Deep nesting (prefer early returns)
- Magic numbers without explanation
- Copy-paste code (extract to functions)
- Unused imports or dead code
"""

# ============================================================================
# Template Registry
# ============================================================================

INPUT_TEMPLATES = {
    # Planning templates
    "planning/story-instructions": {
        "id": "planning/story-instructions",
        "name": "Story Generation Instructions",
        "description": "Master prompt for extracting stories from design documents",
        "loop_type": "planning",
        "tag": "story_instructions",
        "filename": "story-instructions.md",
        "content": STORY_INSTRUCTIONS_CONTENT,
    },
    "planning/story-guardrails": {
        "id": "planning/story-guardrails",
        "name": "Story Quality Guardrails",
        "description": "Quality rules for generated stories",
        "loop_type": "planning",
        "tag": "guardrails",
        "filename": "story-guardrails.md",
        "content": STORY_GUARDRAILS_CONTENT,
    },
    # Implementation templates
    "implementation/impl-instructions": {
        "id": "implementation/impl-instructions",
        "name": "Implementation Instructions",
        "description": "Master prompt for code implementation",
        "loop_type": "implementation",
        "tag": "reference",
        "filename": "impl-instructions.md",
        "content": IMPLEMENTATION_INSTRUCTIONS_CONTENT,
    },
    "implementation/code-guardrails": {
        "id": "implementation/code-guardrails",
        "name": "Code Quality Guardrails",
        "description": "Quality rules for generated code",
        "loop_type": "implementation",
        "tag": "guardrails",
        "filename": "code-guardrails.md",
        "content": CODE_GUARDRAILS_CONTENT,
    },
}


def list_input_templates(loop_type: Optional[str] = None) -> list[dict]:
    """List available input templates.

    Args:
        loop_type: Optional filter by loop type ('planning' or 'implementation').

    Returns:
        List of template info dicts (without content for listing).
    """
    templates = []
    for template_id, template in INPUT_TEMPLATES.items():
        if loop_type and template["loop_type"] != loop_type:
            continue
        templates.append({
            "id": template["id"],
            "name": template["name"],
            "description": template["description"],
            "loop_type": template["loop_type"],
            "tag": template["tag"],
            "filename": template["filename"],
        })
    return templates


def get_input_template(template_id: str) -> Optional[dict]:
    """Get a specific input template with content.

    Args:
        template_id: Template identifier (e.g., 'planning/story-instructions').

    Returns:
        Full template dict including content, or None if not found.
    """
    return INPUT_TEMPLATES.get(template_id)


def get_input_tags() -> dict:
    """Get all available input tags with their descriptions.

    Returns:
        Dict mapping tag ID to label and description.
    """
    return INPUT_TAGS.copy()


def get_required_tags(loop_type: str) -> list[str]:
    """Get required input tags for a loop type.

    Args:
        loop_type: Loop type ('planning' or 'implementation').

    Returns:
        List of required tag IDs.
    """
    return REQUIRED_TAGS_BY_LOOP_TYPE.get(loop_type, [])


def validate_loop_inputs(inputs: list[dict], loop_type: str) -> dict:
    """Validate that a loop has required inputs.

    Args:
        inputs: List of input file dicts with 'tag' field.
        loop_type: Loop type ('planning' or 'implementation').

    Returns:
        Validation result dict with:
        - valid: bool
        - missing_tags: list of missing required tag IDs
        - warnings: list of warning messages
    """
    required_tags = get_required_tags(loop_type)
    existing_tags = {inp.get("tag") for inp in inputs if inp.get("tag")}

    missing = [tag for tag in required_tags if tag not in existing_tags]

    warnings = []
    # Check for common issues
    if loop_type == "implementation":
        has_stories = any(
            inp.get("name", "").endswith(".jsonl") or inp.get("tag") == "stories"
            for inp in inputs
        )
        if not has_stories:
            warnings.append("No JSONL stories file detected")

    return {
        "valid": len(missing) == 0,
        "missing_tags": missing,
        "warnings": warnings,
    }
