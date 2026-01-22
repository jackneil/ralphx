"""
Base loop templates for quick-start configuration.

Templates are global, read-only, and shipped with RalphX.
Users can copy template config into their loop, then modify as needed.
"""

from typing import Optional

# Base loop templates
TEMPLATES: dict[str, dict] = {
    "extractgen_requirements": {
        "name": "extractgen_requirements",
        "display_name": "Extract Requirements Loop",
        "description": "Discover and document user stories from design documents or web research",
        "type": "generator",
        "category": "discovery",
        "config": {
            "name": "extractgen_requirements",
            "display_name": "Extract Requirements Loop",
            "type": "generator",
            "description": "Discover and document user stories from design documents",
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
                    "tools": [],
                    "prompt_template": "prompts/extractgen_requirements_turbo.md",
                },
                {
                    "name": "deep",
                    "description": "Thorough web research for best practices",
                    "model": "claude-sonnet-4-20250514",
                    "timeout": 900,
                    "tools": ["web_search"],
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
                    "tools": ["web_search"],
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
        "display_name": "Implementation Loop",
        "description": "Implement user stories one at a time with test verification",
        "type": "consumer",
        "category": "execution",
        "config": {
            "name": "implementation",
            "display_name": "Implementation Loop",
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
                    "tools": ["file_read", "file_write", "shell"],
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
    "simple_generator": {
        "name": "simple_generator",
        "display_name": "Simple Generator",
        "description": "Basic content generation loop for creating items",
        "type": "generator",
        "category": "generation",
        "config": {
            "name": "generator",
            "display_name": "Content Generator",
            "type": "generator",
            "description": "Generate content items in a loop",
            "item_types": {
                "output": {
                    "singular": "item",
                    "plural": "items",
                    "description": "Generated content",
                }
            },
            "modes": [
                {
                    "name": "default",
                    "description": "Generate content",
                    "model": "claude-sonnet-4-20250514",
                    "timeout": 300,
                    "tools": [],
                    "prompt_template": "prompts/generate.md",
                }
            ],
            "mode_selection": {"strategy": "fixed", "fixed_mode": "default"},
            "limits": {
                "max_iterations": 10,
                "max_consecutive_errors": 3,
            },
        },
    },
    "reviewer": {
        "name": "reviewer",
        "display_name": "Review Loop",
        "description": "Process and review existing items (validate, transform, enhance)",
        "type": "consumer",
        "category": "processing",
        "config": {
            "name": "reviewer",
            "display_name": "Review Loop",
            "type": "consumer",
            "description": "Review and validate existing items",
            "item_types": {
                "input": {
                    "singular": "item",
                    "plural": "items",
                    "source": "generator",
                    "description": "Items to review",
                },
                "output": {
                    "singular": "review",
                    "plural": "reviews",
                    "description": "Review results and recommendations",
                },
            },
            "modes": [
                {
                    "name": "default",
                    "description": "Review one item per iteration",
                    "model": "claude-sonnet-4-20250514",
                    "timeout": 300,
                    "tools": [],
                    "prompt_template": "prompts/review.md",
                }
            ],
            "mode_selection": {"strategy": "fixed", "fixed_mode": "default"},
            "limits": {
                "max_iterations": 0,  # Process all items
                "max_consecutive_errors": 5,
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
