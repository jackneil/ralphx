# {MODE} MODE: Generate {CATEGORY} Stories

## YOUR TASK

{MODE_INSTRUCTION}

**Category Focus:** {CATEGORY} - {CATEGORY_NAME}
{CATEGORY_DESC}

**Use IDs starting at: {NEXT_ID}** (increment for each story)

## RULES

**YOU MUST:**
- Generate {MIN_STORIES}-{MAX_STORIES} NEW user stories for the {CATEGORY} category
- Only create stories that fit this specific category
- Use the format: `{CATEGORY}-XXX` where XXX is the next number
- Output ONLY a raw JSON array at the end - no markdown, no explanation, no code fences

**YOU MUST NOT:**
- Create stories for other categories (focus ONLY on {CATEGORY})
- Duplicate existing stories listed below
- Output anything except the JSON array (at the end)
{MODE_RESTRICTIONS}

---

## EXISTING {CATEGORY} STORIES (do not duplicate these)

{EXISTING_STORIES}

---

## PROJECT DESIGN DOCUMENT

{DESIGN_DOC}

---

{MODE_RESEARCH_SECTION}

## OUTPUT FORMAT

Output a raw JSON array (NO markdown fences, NO explanation):

[{"id":"{CATEGORY}-XXX","priority":50,"story":"As a [role], I can [action] so that [benefit]","acceptance_criteria":["Criterion 1","Criterion 2","Criterion 3"],"status":"pending","category":"{CATEGORY}","notes":"Source: [design doc/research source]"}]

## PRIORITY GUIDE

- 1-20: Core infrastructure (must be first)
- 21-40: Essential workflow (must-have for MVP)
- 41-60: Important features (needed for production)
- 61-80: Advanced features (differentiation)
- 81-100: Nice-to-have (future roadmap)

---

{MODE_FINAL_INSTRUCTION}

OUTPUT THE JSON ARRAY NOW:


---
---
---

# TEMPLATE VARIABLES FOR TURBO MODE

Set {MODE_INSTRUCTION} to:
```
Read the ENTIRE design document below and extract ALL user stories for this category.
```

Set {MODE_RESTRICTIONS} to:
```
- Do NOT use web search - all info is in the design document
```

Set {MODE_RESEARCH_SECTION} to empty string.

Set {MODE_FINAL_INSTRUCTION} to:
```
Extract stories directly from the design document.
```

---
---
---

# TEMPLATE VARIABLES FOR DEEP MODE

Set {MODE_INSTRUCTION} to:
```
Do web research to find NEW user stories that fill gaps not covered by the design document.
```

Set {MODE_RESTRICTIONS} to:
```
- Do NOT write stories for features already fully specified in the design doc
- Do NOT write to any files or run git commands
```

Set {MODE_RESEARCH_SECTION} to:
```
## RESEARCH PROCESS

### Step 1: Understand Existing Coverage
1. Review the design document for {CATEGORY_NAME} sections
2. Review existing {CATEGORY} stories above
3. Note what aspects are already well-covered vs have gaps

### Step 2: Web Research for Gaps

Use WebSearch with queries like:
- "{PROJECT_DESCRIPTION} {CATEGORY_NAME} best practices"
- "{CATEGORY_DESC} software features"
- "{CATEGORY_NAME} industry standards"

**Prioritize authoritative sources:**
- Official documentation
- Industry standards bodies
- Technical specifications
- Best practice guides

### Step 3: Identify Gaps

From your research, find:
- Edge cases not covered by existing stories
- Industry best practices not yet captured
- Technical requirements that are missing
- Integration patterns commonly expected

### Step 4: Create Stories

Write NEW user stories that fill the gaps you identified.
Each story should:
- Address a specific gap found in research
- Be implementable as a software feature
- Include clear acceptance criteria
- Note the source of the requirement
```

Set {MODE_FINAL_INSTRUCTION} to:
```
DO YOUR RESEARCH AND OUTPUT THE JSON ARRAY.
```
