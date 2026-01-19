# Software Development Lifecycle Workflows

## Overview

RalphX provides out-of-box workflow templates for common software development lifecycle (SDLC) activities. These templates capture the patterns that software teams use daily, from building new products to maintaining existing systems.

Each workflow is a **multi-step pipeline** where:
- **Generator steps** create work items (stories, bugs, tasks)
- **Consumer steps** process those items (implement, test, review)
- **Interactive steps** involve human decision-making (approval, prioritization)

---

## Workflow Categories

### 1. Product Development Workflows

#### 1.1 New Product Development (NPD)
**Purpose**: Build a new product from scratch based on a PRD/design doc.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Story Generator │ ──▶ │ Implementation   │ ──▶ │ Integration     │
│ (from PRD)      │     │ (build features) │     │ (connect parts) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
        │                        │                        │
   User Stories           Working Code            Integrated System
   (50-200 items)        (per story)              (tested together)
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. Story Generation | Autonomous | Generator | Extract user stories from PRD/design doc |
| 2. Story Prioritization | Interactive | Consumer | Human reviews and prioritizes each story |
| 3. Implementation | Autonomous | Consumer | Implement each story with tests |
| 4. Code Review | Interactive | Consumer | Human reviews implementations |
| 5. Integration | Autonomous | Consumer | Ensure features work together |

**Metrics:**
- Stories generated
- Stories implemented
- Test coverage %
- Integration success rate

**When to use:**
- Greenfield projects starting from a PRD
- Major rewrites or v2 development
- Hackathon/MVP builds with clear requirements

---

#### 1.2 Feature Enhancement
**Purpose**: Add a new feature to an existing product.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Impact Analysis │ ──▶ │ Task Breakdown   │ ──▶ │ Implementation  │
│ (what changes?) │     │ (from impacts)   │     │ (build it)      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. Impact Analysis | Autonomous | Generator | Analyze codebase for affected areas |
| 2. Task Breakdown | Autonomous | Consumer | Break each impact area into implementable tasks |
| 3. Implementation | Autonomous | Consumer | Implement each task |
| 4. Regression Testing | Autonomous | Consumer | Verify no existing features broke |

**When to use:**
- Adding new capabilities to existing product
- Extending existing features
- Feature requests from customers

---

### 2. Quality & Bug Workflows

#### 2.1 Bug Fix Pipeline
**Purpose**: Triage, investigate, and fix reported bugs.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Bug Triage      │ ──▶ │ Root Cause       │ ──▶ │ Fix & Verify    │
│ (prioritize)    │     │ (investigate)    │     │ (implement fix) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. Bug Import | Autonomous | Generator | Import bugs from issue tracker |
| 2. Triage | Interactive | Consumer | Human prioritizes severity/impact |
| 3. Root Cause Analysis | Autonomous | Consumer | Investigate each bug's cause |
| 4. Fix Implementation | Autonomous | Consumer | Implement and test fix |
| 5. Verification | Autonomous | Consumer | Verify fix doesn't regress |

**Integrations:**
- GitHub Issues
- Jira
- Linear
- Sentry (error tracking)

**When to use:**
- Processing a backlog of reported bugs
- Post-release bug triage
- Support ticket escalations that turned into bugs

---

#### 2.2 Proactive Bug Discovery
**Purpose**: Find bugs before users do.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Code Analysis   │ ──▶ │ Edge Cases       │ ──▶ │ Bug Triage      │
│ (find weak spots)│     │ (from weak spots)│     │ (confirm bugs)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. Static Analysis | Autonomous | Generator | Scan code for potential issues |
| 2. Edge Case Discovery | Autonomous | Consumer | Identify edge cases for each weak spot |
| 3. Test Generation | Autonomous | Consumer | Generate tests for edge cases |
| 4. Bug Confirmation | Autonomous | Consumer | Run tests, log failures as bugs |
| 5. Bug Triage | Interactive | Consumer | Human reviews confirmed bugs |

**Discovery Strategies:**
- Uncovered code paths
- Error handling gaps
- Boundary conditions
- Race conditions
- Security vulnerabilities

**When to use:**
- Before major releases
- After significant refactoring
- Periodic quality sweeps
- When test coverage is below target

---

#### 2.3 Security Audit
**Purpose**: Find and fix security vulnerabilities.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Vulnerability   │ ──▶ │ Severity Triage  │ ──▶ │ Remediation     │
│ Scanning        │     │ (prioritize)     │     │ (fix issues)    │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1-3. Security Scans (parallel) | Autonomous | Generator | Run OWASP, Dependency, and Auth/AuthZ scans |
| 4. Severity Triage | Interactive | Consumer | Human prioritizes all findings by risk |
| 5. Remediation | Autonomous | Consumer | Fix each vulnerability |

**Note:** Steps 1-3 are parallel generators - they run independently and all feed into the Severity Triage consumer. This pattern is valid when multiple independent analyses produce items of the same type (security findings).

**Output Items:**
- CVE-linked vulnerabilities
- Hardcoded secrets
- SQL injection points
- XSS vulnerabilities
- Auth bypass risks

**When to use:**
- Pre-release security review
- After adding new auth/authz code
- Periodic security hygiene
- After dependency updates with security advisories

---

### 3. Predictive & Proactive Workflows

#### 3.1 Feature Request Prediction
**Purpose**: Anticipate user needs before they ask.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Usage Analysis  │ ──▶ │ Friction Points  │ ──▶ │ Feature Ideas   │
│ (patterns)      │     │ (from patterns)  │     │ (from friction) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. Usage Pattern Analysis | Autonomous | Generator | Analyze logs, analytics, support tickets |
| 2. Friction Identification | Autonomous | Consumer | Find bottlenecks within each usage pattern |
| 3. Feature Ideation | Autonomous | Consumer | Generate feature ideas addressing each friction |
| 4. Feasibility Analysis | Autonomous | Consumer | Estimate effort, dependencies |
| 5. Product Review | Interactive | Consumer | Human approves for roadmap |

**Data Sources:**
- Support ticket themes
- Feature request patterns
- User behavior analytics
- Competitive analysis
- Industry trends

**When to use:**
- Product roadmap planning
- Quarterly reviews
- When growth has slowed and you need new ideas
- After acquiring new customer segments

---

#### 3.2 Technical Debt Detection
**Purpose**: Find and prioritize tech debt before it slows you down.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Debt Detection  │ ──▶ │ Impact Analysis  │ ──▶ │ Refactoring     │
│ (find issues)   │     │ (prioritize)     │     │ (clean up)      │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1-2. Debt Scans (parallel) | Autonomous | Generator | Find code smells + outdated dependencies |
| 3. Impact Scoring | Autonomous | Consumer | Score each finding by maintenance burden |
| 4. Prioritization | Interactive | Consumer | Human selects what to fix |
| 5. Refactoring | Autonomous | Consumer | Clean up selected items |

**Note:** Steps 1-2 are parallel generators that both produce tech debt items for scoring.

**Debt Categories:**
- Code complexity (high cyclomatic complexity)
- Outdated dependencies
- Missing tests
- Documentation gaps
- Deprecated API usage
- Performance bottlenecks

**When to use:**
- Sprint planning (allocate debt paydown)
- After rapid feature development periods
- When developer velocity is declining
- Before major architectural changes

---

### 4. Maintenance Workflows

#### 4.1 Dependency Updates
**Purpose**: Keep dependencies current and secure.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Update Check    │ ──▶ │ Compatibility    │ ──▶ │ Upgrade         │
│ (find updates)  │     │ (test changes)   │     │ (apply updates) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. Update Discovery | Autonomous | Generator | Check for available updates |
| 2. Risk Assessment | Autonomous | Consumer | Classify by breaking change risk |
| 3. Compatibility Testing | Autonomous | Consumer | Test each update |
| 4. Update Approval | Interactive | Consumer | Human approves updates |
| 5. Upgrade Execution | Autonomous | Consumer | Apply approved updates |

**When to use:**
- Weekly/monthly maintenance windows
- After security advisories (urgent)
- Before major releases
- When CI is failing due to deprecations

---

#### 4.2 Documentation Sync
**Purpose**: Keep docs accurate with code changes.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Drift Detection │ ──▶ │ Doc Generation   │ ──▶ │ Review          │
│ (find gaps)     │     │ (update docs)    │     │ (human check)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. Code-Doc Diff | Autonomous | Generator | Find code changes without doc updates |
| 2. API Diff | Autonomous | Consumer | Find API changes not documented for each code change |
| 3. Doc Generation | Autonomous | Consumer | Generate/update documentation |
| 4. Human Review | Interactive | Consumer | Human reviews generated docs |

**When to use:**
- After feature releases
- During onboarding reviews
- When support tickets indicate docs are outdated
- Pre-release documentation sweep

---

### 5. Support Workflows

#### 5.1 Support Ticket Resolution
**Purpose**: Resolve support tickets efficiently.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Ticket Import   │ ──▶ │ Classification   │ ──▶ │ Resolution      │
│ (from helpdesk) │     │ (categorize)     │     │ (solve/escalate)│
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. Ticket Import | Autonomous | Generator | Import from support system |
| 2. Classification | Autonomous | Consumer | Categorize: bug, question, feature request |
| 3. Auto-Resolution | Autonomous | Consumer | Attempt resolution with docs/code |
| 4. Human Escalation | Interactive | Consumer | Human handles complex cases |
| 5. Knowledge Update | Autonomous | Consumer | Update docs based on resolutions |

**Note:** Steps 3-5 may run in parallel branches. Auto-resolved tickets go directly to Knowledge Update. Escalated tickets go to Human, then optionally to Knowledge Update if the resolution is generalizable.

**When to use:**
- Ongoing support operations
- When support queue is growing
- To reduce human support load
- After launching new features (support spike expected)

---

#### 5.2 Knowledge Base Enhancement
**Purpose**: Build and improve self-service documentation.

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Gap Analysis    │ ──▶ │ Content Creation │ ──▶ │ Review          │
│ (missing docs)  │     │ (write articles) │     │ (human approve) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
```

**Steps:**
| Step | Type | Loop Type | Description |
|------|------|-----------|-------------|
| 1. FAQ Mining | Autonomous | Generator | Analyze support tickets for common Qs |
| 2. Coverage Analysis | Autonomous | Consumer | Find undocumented features for each FAQ |
| 3. Article Generation | Autonomous | Consumer | Write help articles |
| 4. Human Review | Interactive | Consumer | Human reviews content |
| 5. Publishing | Autonomous | Consumer | Publish to knowledge base |

**When to use:**
- When support deflection rate is low
- After adding major features
- Quarterly documentation refresh
- When onboarding new users

---

## Workflow Composition

### Combining Workflows

Workflows can be **chained** or run in **parallel**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Product Release Workflow                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌──────────────┐    ┌─────────────────────┐ │
│  │ Bug Fix     │    │ Feature      │    │ Security Audit      │ │
│  │ Pipeline    │    │ Enhancement  │    │                     │ │
│  └──────┬──────┘    └──────┬───────┘    └──────────┬──────────┘ │
│         │                  │                       │             │
│         └──────────────────┼───────────────────────┘             │
│                            ▼                                     │
│                   ┌────────────────┐                            │
│                   │ Release        │                            │
│                   │ Candidate      │                            │
│                   └────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow Triggers

Workflows can be triggered by:
- **Manual**: User starts workflow
- **Scheduled**: Cron-like schedule (e.g., daily dependency check)
- **Event**: Git push, PR merge, release tag
- **Threshold**: Error rate spike, test coverage drop
- **Webhook**: External system notification

---

## Workflow Configuration

### Example: Bug Fix Pipeline

```yaml
# ~/.ralphx/templates/workflows/bug-fix-pipeline.yaml
name: bug-fix-pipeline
display_name: "Bug Fix Pipeline"
description: "Triage, investigate, and fix bugs"
category: quality

steps:
  - name: Bug Import
    step_type: autonomous
    loop_type: generator
    config:
      prompt_template: prompts/bug-import.md
      sources:
        - github_issues
        - sentry_errors
      filters:
        labels: ["bug", "defect"]
        state: "open"
      output_schema:
        type: bug
        fields: [title, description, severity, reproduction_steps]

  - name: Triage
    step_type: interactive
    loop_type: consumer
    config:
      prompt_template: prompts/bug-triage.md
      require_human: true
      actions:
        - set_priority
        - assign_owner
        - defer
        - close_as_duplicate

  - name: Root Cause Analysis
    step_type: autonomous
    loop_type: consumer
    config:
      prompt_template: prompts/root-cause.md
      timeout: 300
      tools:
        - Read
        - Grep
        - Glob
      output_fields:
        - root_cause
        - affected_files
        - fix_approach

  - name: Fix Implementation
    step_type: autonomous
    loop_type: consumer
    config:
      prompt_template: prompts/fix-implement.md
      timeout: 600
      tools:
        - Read
        - Write
        - Edit
        - Bash
      validation:
        - tests_pass: true
        - lint_clean: true

  - name: Verification
    step_type: autonomous
    loop_type: consumer
    config:
      prompt_template: prompts/verify-fix.md
      commands:
        - "pytest tests/"
        - "npm run test"
      success_criteria:
        - no_regressions: true
        - original_bug_fixed: true

resources:
  - name: Issue Tracker
    type: github_repo
    config:
      owner: myorg
      repo: myproject
      token: ${GITHUB_TOKEN}

  - name: Error Tracking
    type: sentry
    config:
      project: myproject
      token: ${SENTRY_TOKEN}

guardrails:
  - safety/no-production-access.md
  - domain/bug-fix-guidelines.md
```

### Step Data Flow

Steps pass data to each other through work items. The key mechanism:

1. **Generator steps** create items with a specific `item_type` (defined in `output_schema.type`)
2. **Consumer steps** process items from the previous step(s)
3. Items flow through a shared queue scoped to the workflow run

```yaml
# Explicit input/output binding
steps:
  - name: Impact Analysis
    step_type: autonomous
    loop_type: generator
    config:
      output_schema:
        type: impact_area        # Creates items of type "impact_area"
        fields: [area, files, risk_level]

  - name: Task Breakdown
    step_type: autonomous
    loop_type: consumer
    input_from: Impact Analysis  # Explicitly consumes from previous step
    config:
      input_type: impact_area    # Expects items of type "impact_area"
      output_schema:
        type: task               # Produces items of type "task"
        fields: [title, description, affected_files]
```

**Default behavior:** If `input_from` is not specified, a consumer step processes items from the immediately preceding step.

**Parallel generators:** Multiple generators can run in parallel when they produce items of the same type. Use `parallel_with` to group them:
```yaml
steps:
  - name: OWASP Scan
    step_type: autonomous
    loop_type: generator
    parallel_with: [Dependency Audit, Auth Review]  # Run in parallel

  - name: Dependency Audit
    step_type: autonomous
    loop_type: generator
    parallel_with: [OWASP Scan, Auth Review]

  - name: Severity Triage
    step_type: interactive
    loop_type: consumer
    input_from: [OWASP Scan, Dependency Audit, Auth Review]  # Consumes from all
```

**Branching:** For workflows with conditional routing, use `routing`:
```yaml
  - name: Auto-Resolution
    step_type: autonomous
    loop_type: consumer
    config:
      routing:
        on_success: Knowledge Update    # If resolved
        on_failure: Human Escalation    # If couldn't resolve
```

---

## Metrics & Analytics

### Workflow-Level Metrics

| Metric | Description | Workflows |
|--------|-------------|-----------|
| **Throughput** | Items completed per day | All |
| **Cycle Time** | Time from creation to completion | All |
| **Success Rate** | % items completed without error | All |
| **Human Touch Rate** | % items requiring human intervention | All |

### Step-Level Metrics

| Metric | Description |
|--------|-------------|
| **Generation Rate** | Items created per iteration (generators) |
| **Processing Rate** | Items processed per hour (consumers) |
| **Iteration Time** | Average time per iteration |
| **Error Rate** | Failed iterations % |

### Business Metrics

| Metric | Description | Source Workflow |
|--------|-------------|-----------------|
| **Bug Resolution Time** | Time from report to fix | Bug Fix Pipeline |
| **Feature Velocity** | Features shipped per sprint | Feature Enhancement |
| **Support Deflection** | Tickets resolved without human | Support Resolution |
| **Tech Debt Burn-down** | Debt items resolved per week | Tech Debt Detection |

---

## Template Library Structure

```
~/.ralphx/templates/workflows/
├── product-development/
│   ├── new-product.yaml           # Full NPD workflow
│   ├── feature-enhancement.yaml   # Add feature to existing
│   └── mvp-builder.yaml           # Quick MVP generation
│
├── quality/
│   ├── bug-fix-pipeline.yaml      # Bug triage → fix
│   ├── bug-discovery.yaml         # Proactive bug finding
│   └── security-audit.yaml        # Security scanning
│
├── predictive/
│   ├── feature-prediction.yaml    # Anticipate user needs
│   └── tech-debt-detection.yaml   # Find debt proactively
│
├── maintenance/
│   ├── dependency-updates.yaml    # Keep deps current
│   └── documentation-sync.yaml    # Docs ↔ code alignment
│
├── support/
│   ├── ticket-resolution.yaml     # Resolve support tickets
│   └── knowledge-enhancement.yaml # Build help docs
│
└── composite/
    ├── release-workflow.yaml      # Full release process
    └── continuous-improvement.yaml # Ongoing quality loop
```

---

## Getting Started

### 1. Install a Template

Ask Claude Code:
> "Install the bug-fix-pipeline workflow template for my-app project"

Or manually:
```bash
# List available workflow templates
ralphx templates list

# Install a workflow to your project
ralphx templates install bug-fix-pipeline --project my-app

# Customize the installed workflow
ralphx workflows edit bug-fix-pipeline --project my-app
```

### 2. Configure Resources

Ask Claude Code:
> "Connect my GitHub repo myorg/myproject to RalphX for my-app"

Or manually:
```bash
# Connect your issue tracker
ralphx resources add github \
  --project my-app \
  --owner myorg \
  --repo myproject

# Connect error tracking
ralphx resources add sentry \
  --project my-app \
  --project-id 12345
```

### 3. Run the Workflow

Ask Claude Code:
> "Start the bug-fix-pipeline workflow for my-app"

Or manually:
```bash
# Start the workflow
ralphx run bug-fix-pipeline --project my-app

# Monitor in dashboard
ralphx serve
# Open http://localhost:8765
```

---

## Customization

### Creating Custom Workflows

1. **Start from template**: Copy and modify existing workflow
2. **From scratch**: Define steps, types, and connections
3. **Compose**: Combine multiple workflows into a meta-workflow

### Prompt Engineering

Each step uses a **prompt template** that determines behavior:

```markdown
<!-- prompts/root-cause.md -->
# Root Cause Analysis

You are investigating a bug. Your goal is to find the root cause.

## Bug Details
- Title: {item.title}
- Description: {item.description}
- Reproduction: {item.reproduction_steps}

## Instructions
1. Search the codebase for relevant code
2. Identify the likely source of the bug
3. Document your findings

## Output
Provide:
- `root_cause`: One-line summary of the cause
- `affected_files`: List of files that need changes
- `fix_approach`: High-level approach to fix
```

### Step Type Reference

| Step Type | Loop Type | When to Use |
|-----------|-----------|-------------|
| `autonomous` | `generator` | Create new items from analysis (first step in pipeline) |
| `autonomous` | `consumer` | Process items without human intervention |
| `interactive` | `consumer` | Human decision required per item |
| `interactive` | `none` | Human-only step that doesn't loop over items (e.g., approve entire batch) |

---

## Workflow Selection Guide

### By Team Size

| Context | Recommended Workflows | Notes |
|---------|----------------------|-------|
| **Solo/Small Team (1-5)** | NPD, Bug Fix Pipeline, Dependency Updates | Focus on automation. Skip heavy process workflows. |
| **Medium Team (5-20)** | All above + Security Audit, Tech Debt | Add periodic quality workflows. |
| **Large Team (20+)** | All above + Support, Documentation Sync | Full SDLC coverage with human review gates. |

### By Project Phase

| Phase | Primary Workflows | Secondary |
|-------|------------------|-----------|
| **Ideation** | Feature Request Prediction | - |
| **Development** | NPD, Feature Enhancement | Tech Debt Detection |
| **Maintenance** | Bug Fix Pipeline, Dependency Updates | Documentation Sync |
| **Growth** | Support Ticket Resolution, Knowledge Base | Proactive Bug Discovery |

### By Industry/Compliance

| Context | Required Workflows | Additional Steps |
|---------|-------------------|------------------|
| **Healthcare (HIPAA)** | Security Audit | Add PHI scanning step to all workflows |
| **Finance (SOX/PCI)** | Security Audit, Documentation Sync | Add audit logging to all steps |
| **SaaS** | Bug Fix, Support, Feature Enhancement | Standard workflows suffice |
| **Enterprise** | All workflows | Add approval gates between steps |

### By Codebase Type

| Type | Workflow Adjustments |
|------|---------------------|
| **Monorepo** | Scope workflows to specific packages via filters |
| **Microservices** | Run workflows per-service or use cross-service orchestration |
| **Legacy** | Start with Tech Debt Detection, then Bug Fix Pipeline |
| **Greenfield** | Start with NPD, add others as complexity grows |

---

## Roadmap

### Phase 1: Core Templates
- [x] New Product Development
- [x] Bug Fix Pipeline
- [ ] Feature Enhancement
- [ ] Security Audit

### Phase 2: Integrations
- [ ] GitHub Issues import/export
- [ ] Jira integration
- [ ] Sentry error import
- [ ] Slack notifications

### Phase 3: Advanced
- [ ] Workflow triggers (webhook, schedule)
- [ ] Cross-workflow dependencies
- [ ] Custom step types
- [ ] ML-based prioritization

---

## Design Principles

1. **Start Simple**: Each workflow should be immediately useful with minimal config
2. **Progressive Disclosure**: Advanced features available but not required
3. **Human in the Loop**: Always allow human override and review
4. **Observability**: Clear visibility into what's happening and why
5. **Composability**: Workflows can be combined and extended
6. **Domain Agnostic**: Same patterns apply across industries

---

## Appendix: Workflow Item Schemas

### User Story
```typescript
interface UserStory {
  id: string
  title: string
  description: string
  acceptance_criteria: string[]
  priority: 'critical' | 'high' | 'medium' | 'low'
  story_points?: number
  tags: string[]
}
```

### Bug
```typescript
interface Bug {
  id: string
  title: string
  description: string
  severity: 'critical' | 'major' | 'minor' | 'trivial'
  reproduction_steps: string
  affected_version?: string
  environment?: string
  stack_trace?: string
}
```

### Tech Debt Item
```typescript
interface TechDebtItem {
  id: string
  title: string
  category: 'complexity' | 'outdated' | 'missing_tests' | 'docs' | 'performance'
  impact_score: number  // 1-10
  effort_estimate: 'trivial' | 'small' | 'medium' | 'large'
  affected_files: string[]
  recommendation: string
}
```

### Security Vulnerability
```typescript
interface SecurityVulnerability {
  id: string
  title: string
  cve_id?: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  category: 'injection' | 'auth' | 'xss' | 'exposure' | 'misc'
  affected_code: string
  remediation: string
}
```
