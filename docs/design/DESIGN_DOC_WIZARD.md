# Design Document Creation Wizard

## Overview

Every workflow should have a design document that guides Claude's work. This wizard helps users create comprehensive design documents either externally (using deep research tools) or interactively within RalphX.

## Problem Statement

Currently:
- Users often start workflows without proper design documentation
- Claude operates without context about the project goals, constraints, and requirements
- No guided way to create design docs that capture all necessary information
- Users may not know what a good design doc should contain

## Goals

1. Make it obvious when a workflow lacks a design document
2. Provide multiple paths to create design documents
3. For in-app creation, guide users through an interactive process
4. Leverage Claude to help build comprehensive design documents
5. Store design documents as workflow resources for use in all steps

## User Flow

### Entry Point

When a workflow has no design document, the header shows an amber "No Design Doc" button. Clicking it opens the Design Document Wizard.

```
┌─────────────────────────────────────────────────────────────┐
│  Workflow: Feature Implementation                           │
│  [Draft] [⚠ No Design Doc] [🛡 2 Guardrails]               │
└─────────────────────────────────────────────────────────────┘
```

### Step 1: Choose Creation Method

```
┌─────────────────────────────────────────────────────────────┐
│  Create Design Document                                     │
│                                                             │
│  How would you like to create your design document?         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📄 Upload Existing Document                         │   │
│  │  I already have a design doc, PRD, or spec          │   │
│  │  [Browse files...]                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🔬 Use External Tools (Recommended for complex)     │   │
│  │  Use Claude Code, Deep Research, or other tools     │   │
│  │  to create a thorough design document externally    │   │
│  │  [Show Instructions]                                 │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ✨ Create Interactively (Quick Start)               │   │
│  │  Describe your task and I'll help you build a       │   │
│  │  design document by scanning your project and       │   │
│  │  asking clarifying questions                        │   │
│  │  [Start Interactive Session]                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Option A: Upload Existing Document

Simple file upload flow:
1. User selects a markdown or text file
2. System validates it's a reasonable design document
3. File is stored as a workflow resource
4. Wizard closes, workflow shows green "Design Doc" indicator

### Option B: Use External Tools

Shows instructions for using external tools:

```
┌─────────────────────────────────────────────────────────────┐
│  Create with External Tools                                 │
│                                                             │
│  For complex projects, we recommend using dedicated tools   │
│  to create a thorough design document:                      │
│                                                             │
│  🔹 Claude Deep Research                                    │
│     Best for: Market research, competitive analysis,        │
│     understanding problem domains                           │
│     → Open Claude.ai and use deep research mode            │
│                                                             │
│  🔹 Claude Code                                             │
│     Best for: Technical architecture, codebase analysis,    │
│     implementation planning                                 │
│     → Run: claude "Create a design doc for [your task]"    │
│                                                             │
│  🔹 Manual Creation                                         │
│     Use your favorite editor with our template              │
│     [Download Template]                                     │
│                                                             │
│  Once complete, return here and upload your document.       │
│                                                             │
│  [← Back]                              [Upload Document]    │
└─────────────────────────────────────────────────────────────┘
```

### Option C: Interactive Creation (Main Feature)

#### Step C.1: Describe Your Task

```
┌─────────────────────────────────────────────────────────────┐
│  Tell me about your project                                 │
│                                                             │
│  Describe what you want to accomplish in as much detail     │
│  as you can. Include:                                       │
│  • What problem are you solving?                            │
│  • Who is this for?                                         │
│  • What does success look like?                             │
│  • Any constraints or requirements?                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                       │   │
│  │  I need to add a user authentication system to my    │   │
│  │  React application. Users should be able to sign up  │   │
│  │  with email/password or OAuth (Google, GitHub).      │   │
│  │  Need to support role-based access control with      │   │
│  │  admin and regular user roles...                     │   │
│  │                                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [← Back]                                    [Continue →]   │
└─────────────────────────────────────────────────────────────┘
```

#### Step C.2: Project Analysis

System automatically:
1. Scans the connected project folder for relevant files
2. Identifies tech stack, existing patterns, dependencies
3. Searches web for relevant documentation/best practices

```
┌─────────────────────────────────────────────────────────────┐
│  Analyzing your project...                                  │
│                                                             │
│  ✓ Scanning project files                                   │
│    Found: React 18, TypeScript, Vite, Tailwind             │
│    Existing auth: None detected                             │
│                                                             │
│  ✓ Identifying patterns                                     │
│    State management: React Context                          │
│    API layer: fetch with custom hooks                       │
│    Routing: React Router v6                                 │
│                                                             │
│  ⟳ Researching best practices                              │
│    Searching for: React authentication patterns 2024        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### Step C.3: Interactive Q&A Session

Claude asks clarifying questions to fill in gaps:

```
┌─────────────────────────────────────────────────────────────┐
│  Let's clarify a few things                                 │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🤖 Claude                                            │   │
│  │                                                       │   │
│  │ I've analyzed your project. I have a few questions:  │   │
│  │                                                       │   │
│  │ 1. **Session Management**: Do you want to use        │   │
│  │    JWT tokens (stateless) or server-side sessions    │   │
│  │    (stateful)?                                        │   │
│  │                                                       │   │
│  │ 2. **Password Requirements**: Any specific rules     │   │
│  │    for password strength?                             │   │
│  │                                                       │   │
│  │ 3. **Email Verification**: Should users verify       │   │
│  │    their email before accessing the app?              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ Type your answers...                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [← Back]                           [Generate Document →]   │
└─────────────────────────────────────────────────────────────┘
```

#### Step C.4: Review & Save

Claude generates the design document, user can review and edit:

```
┌─────────────────────────────────────────────────────────────┐
│  Review Your Design Document                                │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ # User Authentication System                         │   │
│  │                                                       │   │
│  │ ## Overview                                           │   │
│  │ Add authentication to the React application with     │   │
│  │ email/password and OAuth support...                   │   │
│  │                                                       │   │
│  │ ## Requirements                                       │   │
│  │ ### Functional                                        │   │
│  │ - User registration with email/password              │   │
│  │ - OAuth login (Google, GitHub)                        │   │
│  │ - Role-based access control (admin, user)            │   │
│  │ - Email verification required                         │   │
│  │ ...                                                   │   │
│  │                                                       │   │
│  │ ## Technical Approach                                 │   │
│  │ - JWT tokens stored in httpOnly cookies              │   │
│  │ - React Context for auth state                        │   │
│  │ ...                                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  [← Revise]    [Edit Manually]    [Save & Use Document →]  │
└─────────────────────────────────────────────────────────────┘
```

## Technical Implementation

### Backend

#### New Endpoints

```python
# POST /api/projects/{slug}/workflows/{workflow_id}/design-doc/generate
# Start design document generation session
{
    "task_description": "User's initial description",
    "scan_project": true,  # Whether to scan project files
    "web_search": true     # Whether to search for context
}

# Response: Session ID for streaming updates
{
    "session_id": "gen_abc123",
    "status": "analyzing"
}

# GET /api/projects/{slug}/workflows/{workflow_id}/design-doc/session/{session_id}/stream
# SSE stream for generation progress and Q&A

# POST /api/projects/{slug}/workflows/{workflow_id}/design-doc/session/{session_id}/respond
# Send user responses to Claude's questions
{
    "message": "User's response to questions"
}

# POST /api/projects/{slug}/workflows/{workflow_id}/design-doc/save
# Save the generated document
{
    "content": "# Design Document\n...",
    "filename": "design-doc.md"
}
```

#### Design Doc Generator Service

```python
class DesignDocGenerator:
    """Service for generating design documents interactively."""

    def __init__(self, project_path: Path, workflow_id: str):
        self.project_path = project_path
        self.workflow_id = workflow_id
        self.conversation_history = []

    async def start_session(
        self,
        task_description: str,
        scan_project: bool = True,
        web_search: bool = True
    ) -> AsyncGenerator[dict, None]:
        """Start a design doc generation session."""

        # Phase 1: Project analysis
        if scan_project:
            yield {"phase": "scanning", "message": "Scanning project files..."}
            project_context = await self._scan_project()
            yield {"phase": "scanning", "context": project_context}

        # Phase 2: Web research
        if web_search:
            yield {"phase": "researching", "message": "Researching best practices..."}
            research_context = await self._web_search(task_description)
            yield {"phase": "researching", "context": research_context}

        # Phase 3: Generate clarifying questions
        yield {"phase": "questions", "message": "Generating questions..."}
        questions = await self._generate_questions(
            task_description, project_context, research_context
        )
        yield {"phase": "questions", "questions": questions}

    async def respond_and_generate(
        self, user_response: str
    ) -> AsyncGenerator[dict, None]:
        """Process user response and generate document."""

        self.conversation_history.append({
            "role": "user",
            "content": user_response
        })

        # Check if we need more questions
        needs_more = await self._needs_clarification()
        if needs_more:
            questions = await self._generate_followup_questions()
            yield {"phase": "questions", "questions": questions}
            return

        # Generate document
        yield {"phase": "generating", "message": "Generating design document..."}
        async for chunk in self._generate_document():
            yield {"phase": "generating", "content": chunk}

        yield {"phase": "complete"}

    async def _scan_project(self) -> dict:
        """Scan project for tech stack, patterns, etc."""
        # Use existing codebase scanning logic
        # Return structured context about the project

    async def _web_search(self, query: str) -> dict:
        """Search web for relevant context."""
        # Use web search tool
        # Return relevant findings

    async def _generate_questions(self, ...) -> list[str]:
        """Generate clarifying questions using Claude."""

    async def _generate_document(self) -> AsyncGenerator[str, None]:
        """Stream the generated design document."""
```

### Frontend

#### New Components

```
frontend/src/components/workflow/
├── DesignDocWizard.tsx          # Main wizard modal
├── DesignDocUpload.tsx          # File upload option
├── DesignDocExternal.tsx        # External tools instructions
├── DesignDocInteractive.tsx     # Interactive creation flow
│   ├── TaskDescriptionStep.tsx  # Initial description input
│   ├── AnalysisStep.tsx         # Project analysis display
│   ├── QASessionStep.tsx        # Interactive Q&A with Claude
│   └── ReviewStep.tsx           # Review and edit generated doc
└── DesignDocPreview.tsx         # Markdown preview component
```

#### Wizard State Management

```typescript
interface DesignDocWizardState {
  step: 'choose' | 'upload' | 'external' | 'describe' | 'analyze' | 'qa' | 'review'
  taskDescription: string
  projectContext: ProjectContext | null
  researchContext: ResearchContext | null
  conversation: Message[]
  generatedDocument: string
  isGenerating: boolean
  error: string | null
}
```

### Database Changes

None required - design documents are stored as workflow resources using the existing `workflow_resources` table with `resource_type = 'design_doc'`.

## Design Document Template

The generated document follows this structure:

```markdown
# [Project/Feature Name] Design Document

## Overview
Brief description of what this document covers.

## Problem Statement
What problem are we solving? Why is it important?

## Goals
- Primary goal
- Secondary goals
- Non-goals (explicitly out of scope)

## User Stories
- As a [user], I want to [action] so that [benefit]

## Requirements

### Functional Requirements
- FR1: Description
- FR2: Description

### Non-Functional Requirements
- NFR1: Performance requirements
- NFR2: Security requirements

## Technical Approach

### Architecture
High-level architecture decisions.

### Key Components
- Component 1: Purpose and responsibilities
- Component 2: Purpose and responsibilities

### Data Model
Relevant data structures and their relationships.

### API Design
Key API endpoints or interfaces.

## Implementation Notes

### Dependencies
- Dependency 1: Why it's needed
- Dependency 2: Why it's needed

### Considerations
- Edge cases to handle
- Potential pitfalls
- Security considerations

## Success Criteria
How do we know when we're done?

## Open Questions
- Question 1
- Question 2
```

## Implementation Phases

### Phase 1: Basic Upload (MVP)
- "No Design Doc" indicator in workflow header
- Simple file upload modal
- Store as workflow resource
- Update indicator on success

### Phase 2: External Tools Guide
- Add "Use External Tools" option
- Show instructions for Claude Code, Deep Research
- Download template button

### Phase 3: Interactive Creation
- Task description input
- Project file scanning
- Claude Q&A session
- Document generation
- Review and edit interface

### Phase 4: Enhancements
- Web search integration
- Better project analysis
- Document versioning
- Edit existing design docs

## Success Metrics

1. **Adoption**: % of workflows with design documents attached
2. **Completion**: % of users who complete the wizard vs abandon
3. **Quality**: User satisfaction with generated documents
4. **Workflow Success**: Correlation between having design docs and workflow completion

## Open Questions

1. Should we allow multiple design documents per workflow?
2. How do we handle design doc updates mid-workflow?
3. Should design docs be versioned?
4. Integration with existing planning chat?
