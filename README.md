# RalphX

**Generic Agent Loop Orchestration System**

RalphX is a domain-agnostic framework for building and running autonomous AI agent loops with a modern web dashboard. Define your agent workflows in YAML, run them with any LLM backend, and monitor everything in real-time.

## Features

- **Declarative Loop Definitions** - Define agent workflows in YAML, not code
- **Real-time Dashboard** - Monitor loop progress, view logs, control execution
- **Multiple LLM Backends** - Claude CLI, Anthropic API, OpenAI, Ollama
- **Work Item Management** - Track generated/consumed items with categories and phases
- **Production Ready** - Error handling, timeouts, graceful shutdown, persistence

## Quick Start

```bash
# Install
pip install ralphx

# Create a loop configuration
cat > my_loop.yaml << 'EOF'
name: my_research
display_name: "My Research Loop"
type: generator

modes:
  default:
    timeout: 300
    model: sonnet
    tools: [WebSearch]
    prompt_template: prompts/research.md

mode_selection:
  strategy: fixed
  fixed_mode: default

output:
  format: jsonl
  path: data/items.jsonl
  schema:
    required: [id, content, status]

limits:
  max_iterations: 10
  max_consecutive_errors: 3
EOF

# Run the loop
ralphx run my_loop.yaml

# Or start the dashboard
ralphx serve
```

## Architecture

```
┌─────────────────────────────────────────────┐
│           RalphX Dashboard (React)          │
├─────────────────────────────────────────────┤
│  Loop Control │ Work Items │ Live Logs      │
└─────────────────────────────────────────────┘
                    │ SSE
                    ▼
┌─────────────────────────────────────────────┐
│            RalphX API (FastAPI)             │
├─────────────────────────────────────────────┤
│  /loops  │  /items  │  /stream  │  /config  │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│          RalphX Core (Python)               │
├─────────────────────────────────────────────┤
│  Loop Executor │ LLM Adapters │ Stores      │
└─────────────────────────────────────────────┘
```

## Documentation

- [Design Overview](design/DESIGN.md) - Full system design and architecture
- [Loop Schema](design/LOOP_SCHEMA.md) - Complete YAML configuration reference
- [API Specification](design/API_SPEC.md) - REST API documentation

## Example Use Cases

### PRD Research (Ralph-style)
Generate user stories from design documents and web research.

### Code Review Loop
Automatically review code changes for security and style issues.

### Documentation Generator
Generate API docs from source code.

### Content Pipeline
Research topics and generate content at scale.

## Inspired By

RalphX is inspired by the Ralph system used in the HANK RCM project - an autonomous agent that continuously researches and implements features. RalphX generalizes these patterns into a reusable framework.

## License

MIT
