# Generator Loop Template

You are generating work items based on requirements and context provided.

## Your Task

Analyze the provided context and generate structured work items.

## Guidelines

1. **Analyze requirements** - Understand what needs to be built
2. **Break down into items** - Create discrete, implementable work items
3. **Include details** - Each item should be self-contained with clear scope
4. **Consider dependencies** - Order items logically
5. **Assign categories** - Tag items appropriately

## Output Format

Generate work items in JSON format:

```json
{
  "id": "ITEM-001",
  "title": "Brief title",
  "description": "Detailed description of what needs to be done",
  "category": "feature|bugfix|refactor|infrastructure",
  "priority": "high|medium|low",
  "dependencies": ["ITEM-000"]
}
```

## Context

{{design_doc}}

{{custom_context}}
