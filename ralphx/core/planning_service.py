"""Planning chat service for interactive planning with Claude.

Provides streaming chat functionality for the planning step of workflows.
Uses ClaudeCLIAdapter for consistent credential handling.

Prompt Architecture:
- Layer 1: Format rules (immutable, machine-parsed requirements)
- Layer 2: Behavioral instructions (personality, role)
- Layer 3: Conversation context (message history)
- Layer 4: Current request (user input or generation instruction)

Security Notes:
- User content is sanitized to prevent XML/prompt injection
- Role values are strictly validated
- Error messages are sanitized before returning to clients
"""

import logging
import re
from pathlib import Path
from typing import AsyncIterator, Optional

from ralphx.adapters.claude_cli import ClaudeCLIAdapter
from ralphx.adapters.base import AdapterEvent, StreamEvent
from ralphx.core.project import Project

logger = logging.getLogger(__name__)


# Valid message roles - reject anything else
VALID_ROLES = frozenset({"user", "assistant"})


# =============================================================================
# LAYER 1: FORMAT RULES (immutable, machine-parsed)
# =============================================================================

ARTIFACT_FORMAT_RULES = '''<format_rules>
## CRITICAL OUTPUT FORMAT REQUIREMENTS

You MUST structure your ENTIRE response using these exact XML tags:

<design_doc>
[Your full design document in markdown]
</design_doc>

<guardrails>
[Your project guardrails in markdown]
</guardrails>

RULES:
1. Your response MUST start with <design_doc>
2. Your response MUST contain both tags
3. Do NOT include any text outside these tags
4. Do NOT modify the tag names
5. The content inside tags should be valid markdown

This format is machine-parsed. Non-compliance breaks the system.
</format_rules>'''


# =============================================================================
# LAYER 2: BEHAVIORAL INSTRUCTIONS (personality, role)
# =============================================================================

PLANNING_BEHAVIOR = '''<behavior>
You are an expert product architect and technical consultant helping users design
software products. You combine deep technical knowledge with strong product sense.

## Your Core Mission

Transform vague ideas into comprehensive, implementable design documents through
collaborative discovery. You're not just a Q&A bot—you're a thinking partner who
challenges assumptions, identifies blind spots, and brings industry expertise.

## Discovery Phases

Work through these phases naturally (you don't need to announce them):

### Phase 1: Problem Space Understanding
- What problem are we solving? Why does it matter?
- Who experiences this problem? (specific personas, not generic "users")
- What do they currently do? What's broken about that?
- What would success look like for them?

### Phase 2: Solution Requirements
- Core features (MVP vs nice-to-have)
- User workflows and key interactions
- Data the system needs to handle
- Integration points with other systems
- Constraints: budget, timeline, team skills, existing infrastructure

### Phase 3: Technical Architecture
- System components and how they communicate
- Data model and storage choices
- API design (if applicable)
- Authentication and authorization approach
- Third-party services and dependencies

### Phase 4: Infrastructure & Operations
- Hosting environment (cloud provider, on-prem, hybrid)
- Deployment strategy (containers, serverless, VMs)
- Scaling considerations
- Monitoring and observability
- Backup and disaster recovery

### Phase 5: Security & Compliance
- Data sensitivity and protection requirements
- Authentication mechanisms
- Compliance requirements (GDPR, HIPAA, SOC2, etc.)
- Threat model considerations

## How to Ask Questions

Ask 2-4 focused questions at a time. For each question:
- Explain WHY you're asking (what decision it informs)
- Offer concrete options when helpful, not just open-ended questions
- Share your initial thinking or recommendation if you have one

Good: "For authentication, are you thinking OAuth (Google/GitHub login) for simplicity,
or do you need custom username/password? OAuth is faster to implement and more secure,
but custom auth gives you more control over the user experience."

Bad: "How do you want to handle authentication?"

## Using Web Search

When you have web search available, use it strategically:
- Research industry best practices for the specific domain
- Look up current pricing/capabilities of services you might recommend
- Find examples of similar products for inspiration
- Verify technical approaches are current (technologies evolve fast)
- Look for common pitfalls in this type of application

IMPORTANT: Always tell the user when you're searching and summarize what you learned.
This builds trust and shows you're doing real research, not just making things up.

## Progressive Refinement

As you learn more:
- Periodically summarize your understanding ("Here's what I have so far...")
- Explicitly call out assumptions you're making
- Revisit earlier decisions if new information changes things
- Be willing to push back if something doesn't make sense

## Re-engagement Support

If the user is returning to continue or update an existing design doc:
- Acknowledge what exists and ask what they want to change
- Don't re-ask questions that are already answered in the doc
- Focus on the delta—what's new, changed, or needs refinement

## Offering to Generate

When you have enough information for a solid design document:
- Summarize the key decisions that have been made
- List any important questions that remain unanswered
- Offer to generate the design doc (the user will click a button)

The user can generate the document at ANY time—it doesn't have to be "complete."
Better to generate something and iterate than to wait forever for perfection.

## What NOT To Do

- Don't write code or implementation details (that's for later steps)
- Don't make major assumptions without confirming
- Don't be a yes-person—challenge ideas that seem problematic
- Don't overwhelm with too many questions
- Don't be generic—tailor advice to their specific situation
</behavior>'''

ARTIFACT_BEHAVIOR = '''<behavior>
You are generating structured output from a planning conversation.
Create comprehensive, well-organized documentation.

The design document should include:
- Executive Summary
- Problem Statement
- Target Users
- Core Features (prioritized)
- Technical Architecture
- Data Model (if applicable)
- API Endpoints (if applicable)
- Security Considerations
- Success Metrics

The guardrails should include:
- Coding standards
- Testing requirements
- Git practices
- Security requirements
</behavior>'''


class PlanningService:
    """Service for interactive planning chat with Claude.

    Uses a layered prompt architecture for reliable, parseable outputs.
    """

    def __init__(self, project: Project, project_id: Optional[str] = None):
        """Initialize the planning service.

        Args:
            project: Project object with path and metadata.
            project_id: Optional project ID for credential lookup.
        """
        self.project = project
        self.project_id = project_id

    @staticmethod
    def _sanitize_content(content: str) -> str:
        """Sanitize user content to prevent XML/prompt injection.

        Escapes XML-like tags that could break the prompt structure or
        inject malicious instructions.

        Args:
            content: Raw user content.

        Returns:
            Sanitized content safe for inclusion in prompts.
        """
        if not content:
            return ""

        # Escape characters that could break XML structure
        # We use a custom approach rather than full HTML escaping to preserve
        # most formatting while blocking injection vectors
        sanitized = content

        # Escape angle brackets in tag-like patterns to prevent injection
        # This targets patterns like </human>, <system>, etc.
        # but preserves angle brackets in code examples like "x < y" or "array<int>"
        dangerous_tags = [
            "human", "assistant", "system", "context", "behavior",
            "format_rules", "request", "design_doc", "guardrails",
        ]
        for tag in dangerous_tags:
            # Escape opening tags: <tag> or <tag ...>
            sanitized = re.sub(
                rf'<\s*{tag}(\s|>)',
                rf'&lt;{tag}\1',
                sanitized,
                flags=re.IGNORECASE,
            )
            # Escape closing tags: </tag>
            sanitized = re.sub(
                rf'</\s*{tag}\s*>',
                rf'&lt;/{tag}&gt;',
                sanitized,
                flags=re.IGNORECASE,
            )

        return sanitized

    @staticmethod
    def _validate_role(role: str) -> str:
        """Validate and normalize message role.

        Args:
            role: The role string from the message.

        Returns:
            Validated role ("user" or "assistant").

        Note:
            Invalid roles default to "user" with a warning logged.
        """
        if role not in VALID_ROLES:
            logger.warning(
                f"Invalid message role '{role}' - defaulting to 'user'. "
                "This may indicate a client-side bug or injection attempt."
            )
            return "user"
        return role

    def _format_messages(self, messages: list[dict]) -> str:
        """Format conversation messages for context layer.

        Args:
            messages: List of message dicts with 'role' and 'content'.

        Returns:
            Formatted conversation string with sanitized content.
        """
        parts = []
        for msg in messages:
            role = self._validate_role(msg.get("role", "user"))
            content = self._sanitize_content(msg.get("content", ""))
            if role == "user":
                parts.append(f"<human>\n{content}\n</human>")
            else:
                parts.append(f"<assistant>\n{content}\n</assistant>")
        return "\n\n".join(parts)

    def _build_chat_prompt(self, messages: list[dict]) -> str:
        """Build prompt for conversational chat (no strict format needed).

        Args:
            messages: Conversation history.

        Returns:
            Full prompt string.
        """
        # Layer 2: Behavior
        parts = [f"<system>\n{PLANNING_BEHAVIOR}\n</system>"]

        # Layer 3: Context
        if messages:
            parts.append(f"<context>\n{self._format_messages(messages)}\n</context>")

        return "\n\n".join(parts)

    def _build_artifact_prompt(self, messages: list[dict]) -> str:
        """Build prompt for artifact generation (strict format required).

        Args:
            messages: Conversation history to generate from.

        Returns:
            Full prompt string with format enforcement.
        """
        parts = []

        # Layer 1: Format Rules (FIRST - most important)
        parts.append(ARTIFACT_FORMAT_RULES)

        # Layer 2: Behavior
        parts.append(ARTIFACT_BEHAVIOR)

        # Layer 3: Context
        parts.append(f"<context>\n{self._format_messages(messages)}\n</context>")

        # Layer 4: Request
        parts.append('''<request>
Based on the planning conversation above, generate:
1. A comprehensive design document
2. Project guardrails/coding standards

IMPORTANT: Your response MUST use the exact XML format specified in format_rules.
Start your response with <design_doc> immediately.
</request>''')

        return "\n\n".join(parts)

    async def stream_response(
        self,
        messages: list[dict],
        model: str = "sonnet",
        tools: Optional[list[str]] = None,
        timeout: int = 180,
    ) -> AsyncIterator[StreamEvent]:
        """Stream Claude's response to the conversation.

        For chat responses, no strict format is enforced - just natural conversation.

        Args:
            messages: Conversation history.
            model: Model to use (sonnet, opus, haiku).
            tools: Optional list of tools to enable (e.g., ['WebSearch', 'WebFetch']).
            timeout: Timeout in seconds (default 180 for web search).

        Yields:
            StreamEvent objects as Claude responds.
        """
        adapter = ClaudeCLIAdapter(
            project_path=Path(self.project.path),
            project_id=self.project_id,
        )

        prompt = self._build_chat_prompt(messages)

        async for event in adapter.stream(
            prompt=prompt,
            model=model,
            tools=tools,
            timeout=timeout,
        ):
            yield event

    async def generate_artifacts(
        self,
        messages: list[dict],
        model: str = "sonnet",
    ) -> AsyncIterator[StreamEvent]:
        """Generate design doc and guardrails from conversation.

        Uses strict XML format enforcement for reliable parsing.

        Args:
            messages: Conversation history to generate artifacts from.
            model: Model to use.

        Yields:
            StreamEvent objects as Claude generates artifacts.
        """
        adapter = ClaudeCLIAdapter(
            project_path=Path(self.project.path),
            project_id=self.project_id,
        )

        prompt = self._build_artifact_prompt(messages)

        async for event in adapter.stream(
            prompt=prompt,
            model=model,
            tools=None,
            timeout=180,  # Allow more time for artifact generation
        ):
            yield event

    @staticmethod
    def parse_artifacts(text: str) -> dict:
        """Parse XML-tagged artifacts with fallback.

        Args:
            text: Full text output from artifact generation.

        Returns:
            Dict with 'design_doc', 'guardrails', and optional '_parsing_fallback' keys.
        """
        result = {"design_doc": None, "guardrails": None}

        # Primary: XML parsing
        design_match = re.search(
            r'<design_doc>\s*(.*?)\s*</design_doc>',
            text,
            re.DOTALL,
        )
        if design_match:
            result["design_doc"] = design_match.group(1).strip()

        guardrails_match = re.search(
            r'<guardrails>\s*(.*?)\s*</guardrails>',
            text,
            re.DOTALL,
        )
        if guardrails_match:
            result["guardrails"] = guardrails_match.group(1).strip()

        # Secondary: Try old markdown markers for backwards compatibility
        if not result["design_doc"]:
            old_design_match = re.search(
                r"## DESIGN_DOC_START ##\s*\n(.*?)\n## DESIGN_DOC_END ##",
                text,
                re.DOTALL,
            )
            if old_design_match:
                result["design_doc"] = old_design_match.group(1).strip()
                result["_parsing_fallback"] = "markdown_markers"

        if not result["guardrails"]:
            old_guardrails_match = re.search(
                r"## GUARDRAILS_START ##\s*\n(.*?)\n## GUARDRAILS_END ##",
                text,
                re.DOTALL,
            )
            if old_guardrails_match:
                result["guardrails"] = old_guardrails_match.group(1).strip()

        # Fallback: If no tags found but has substantial content, use heuristics
        if not result["design_doc"] and len(text) > 200:
            # Look for design-doc-like structure
            if "# " in text or "## " in text:
                logger.warning("No XML tags found, using raw text as design doc")
                result["design_doc"] = text.strip()
                result["_parsing_fallback"] = "raw_text"

        return result
