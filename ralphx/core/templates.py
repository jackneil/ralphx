"""
Base loop templates for quick-start configuration.

Templates map 1:1 to workflow step processing types:
- design_doc: Interactive planning with web research
- extractgen_requirements: Extract user stories from design documents
- webgen_requirements: Discover requirements via web research
- implementation: Implement user stories with code changes

Templates are global, read-only, and shipped with RalphX.
Users can copy template config into their loop, then modify as needed.
"""

from typing import Optional

# Base loop templates — one per processing_type
TEMPLATES: dict[str, dict] = {
    "design_doc": {
        "name": "design_doc",
        "display_name": "Design Document",
        "description": "Interactive planning chat to build a design document with web research",
        "type": "generator",
        "category": "planning",
        "default_tools": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
        "config": {
            "name": "design_doc",
            "display_name": "Design Document",
            "type": "generator",
            "description": "Build a comprehensive design document through interactive planning",
            "item_types": {
                "output": {
                    "singular": "artifact",
                    "plural": "artifacts",
                    "description": "Design document and guardrails",
                }
            },
            "modes": [
                {
                    "name": "default",
                    "description": "Interactive planning with web research",
                    "model": "claude-sonnet-4-20250514",
                    "timeout": 300,
                    "tools": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
                    "prompt_template": "prompts/planning.md",
                }
            ],
            "mode_selection": {"strategy": "fixed", "fixed_mode": "default"},
            "limits": {
                "max_iterations": 100,
                "max_runtime_seconds": 28800,
                "max_consecutive_errors": 5,
                "cooldown_between_iterations": 5,
            },
        },
    },
    "extractgen_requirements": {
        "name": "extractgen_requirements",
        "display_name": "Extract Requirements",
        "description": "Extract user stories from design documents",
        "type": "generator",
        "category": "discovery",
        "default_tools": ["Read", "Glob", "Grep"],
        "config": {
            "name": "extractgen_requirements",
            "display_name": "Extract Requirements",
            "type": "generator",
            "description": "Extract and generate user stories from design documents",
            "item_types": {
                "output": {
                    "singular": "story",
                    "plural": "stories",
                    "description": "User stories with acceptance criteria",
                }
            },
            "modes": [
                {
                    "name": "turbo",
                    "description": "Fast extraction from design docs (no web search)",
                    "model": "claude-sonnet-4-20250514",
                    "timeout": 180,
                    "tools": ["Read", "Glob", "Grep"],
                    "prompt_template": "prompts/extractgen_requirements_turbo.md",
                },
                {
                    "name": "deep",
                    "description": "Thorough web research for best practices",
                    "model": "claude-sonnet-4-20250514",
                    "timeout": 900,
                    "tools": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
                    "prompt_template": "prompts/extractgen_requirements_deep.md",
                },
            ],
            "mode_selection": {
                "strategy": "weighted_random",
                "weights": {"turbo": 85, "deep": 15},
            },
            "limits": {
                "max_iterations": 100,
                "max_runtime_seconds": 28800,
                "max_consecutive_errors": 5,
                "cooldown_between_iterations": 5,
            },
        },
    },
    "webgen_requirements": {
        "name": "webgen_requirements",
        "display_name": "Web-Generated Requirements",
        "description": "Discover missing requirements through web research on domain best practices",
        "type": "generator",
        "category": "discovery",
        "default_tools": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
        "config": {
            "name": "webgen_requirements",
            "display_name": "Web-Generated Requirements",
            "type": "generator",
            "description": "Research industry best practices to find requirements NOT in the design doc",
            "item_types": {
                "output": {
                    "singular": "story",
                    "plural": "stories",
                    "description": "User stories discovered through domain research",
                }
            },
            "modes": [
                {
                    "name": "research",
                    "description": "Web research for best practices and gaps",
                    "model": "claude-sonnet-4-20250514",
                    "timeout": 900,
                    "tools": ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
                    "prompt_template": "prompts/webgen_requirements.md",
                }
            ],
            "mode_selection": {"strategy": "fixed", "fixed_mode": "research"},
            "limits": {
                "max_iterations": 15,
                "max_runtime_seconds": 14400,
                "max_consecutive_errors": 3,
                "cooldown_between_iterations": 15,
            },
        },
    },
    "implementation": {
        "name": "implementation",
        "display_name": "Implementation",
        "description": "Implement user stories one at a time with test verification",
        "type": "consumer",
        "category": "execution",
        "default_tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
        "config": {
            "name": "implementation",
            "display_name": "Implementation",
            "type": "consumer",
            "description": "Implement user stories with automated testing",
            "item_types": {
                "input": {
                    "singular": "story",
                    "plural": "stories",
                    "source": "extractgen_requirements",
                    "description": "Stories to implement",
                },
                "output": {
                    "singular": "implementation",
                    "plural": "implementations",
                    "description": "Completed feature with passing tests",
                },
            },
            "modes": [
                {
                    "name": "default",
                    "description": "Implement one story per iteration",
                    "model": "claude-sonnet-4-20250514",
                    "timeout": 1800,
                    "tools": ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
                    "prompt_template": "prompts/implementation.md",
                }
            ],
            "mode_selection": {"strategy": "fixed", "fixed_mode": "default"},
            "limits": {
                "max_iterations": 50,
                "max_runtime_seconds": 28800,
                "max_consecutive_errors": 3,
            },
        },
    },
}


def get_template(name: str) -> Optional[dict]:
    """Get a template by name.

    Args:
        name: Template name (e.g., 'extractgen_requirements', 'implementation')

    Returns:
        Template dict or None if not found
    """
    return TEMPLATES.get(name)


def get_default_tools(processing_type: str) -> Optional[list[str]]:
    """Get default tools for a processing type.

    Args:
        processing_type: Step processing type (design_doc, extractgen_requirements, etc.)

    Returns:
        List of tool names, or None if not found.
    """
    template = TEMPLATES.get(processing_type)
    if template:
        return template.get("default_tools")
    return None


def list_templates() -> list[dict]:
    """List all available templates.

    Returns:
        List of template metadata (without full config for listing)
    """
    return [
        {
            "name": t["name"],
            "display_name": t["display_name"],
            "description": t["description"],
            "type": t["type"],
            "category": t["category"],
            "default_tools": t.get("default_tools"),
        }
        for t in TEMPLATES.values()
    ]


def get_template_config(name: str) -> Optional[dict]:
    """Get just the config portion of a template (for creating loops).

    Args:
        name: Template name

    Returns:
        Config dict ready to be converted to YAML, or None
    """
    template = TEMPLATES.get(name)
    if template:
        return template["config"]
    return None
