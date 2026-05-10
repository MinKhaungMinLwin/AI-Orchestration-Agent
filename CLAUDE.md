# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea using a multi-agent FastAPI architecture.

### Services
| Service | Port | Description |
|---------|------|-------------|
| tstation-ai | 9000 | Main AI service (FastAPI) with LangChain agents, RAG (Qdrant), Celery/Redis |
| tstation-be | 8000 | Backend service connecting to Oracle database |
| tstation-ui-demo | 7777 | Streamlit-based demo UI |

## Karpathy-Inspired Coding Guidelines

Before coding, reviewing, or refactoring:

1. Think Before Coding
   - State assumptions explicitly.
   - If uncertain, ask instead of guessing.
   - Present trade-offs when multiple approaches exist.
   - Push back if a simpler approach is better.

2. Simplicity First
   - Write the minimum code that solves the task.
   - Do not add speculative features or abstractions.
   - Avoid configurability or flexibility that was not requested.
   - If the solution is bloated, simplify it.

3. Surgical Changes
   - Touch only files and lines required by the task.
   - Do not refactor unrelated code.
   - Match existing project style.
   - Do not delete unrelated dead code unless asked.

4. Goal-Driven Execution
   - Define success criteria before implementation.
   - Prefer tests or verifiable checks.
   - Loop until the requested outcome is verified.

## Common Commands

### Setup
```bash
just setup              # Clear venv, install deps, setup local config
just install-hooks      # Install pre-commit hooks
source .venv/bin/activate
```

### Code Quality
```bash
just lint               # Check code with ruff
just fmt                # Format code with ruff + isort
```

### OpenAPI Client Regeneration
```bash
just update-openapi     # Regenerate tstation-be API client from openapi spec
```

### Docker Deployment
```bash
just start              # Start services (ENV=local → local compose, else remote)
just stop               # Stop services (ENV-aware)
just start-local        # Explicit local Docker start
just start-remote       # Explicit remote Docker start (dev|stag|prod)
ENV=dev just start      # Remote deployment shorthand
```

## Architecture

### Agent Structure (`app/tstation-ai/services/tstation/agents/`)

Each domain agent inherits `BaseAgent` (see `base_agent.py`). `router.py` instantiates all agents as module-level singletons and exposes `AgentDomain.get_agent()` for dispatch.

| Prefix | Agent | Domain | Description |
|--------|-------|--------|-------------|
| a_ | leading_agent | LEADING | Primary orchestrator, greeting, complaint handling |
| b_ | discovery_agent | DISCOVERY | Product recommendations, compatibility, vehicle lookup |
| c_ | transaction_agent | TRANSACTION | Orders, pricing, stock, store search |
| e_ | support_agent | SUPPORT | Warranty, returns, FAQ, 1:1 escalation |
| f_ | ui_template_agent | (deprecated) | UI formatting; being removed in current refactor |
| g_ | qc_agent | (cross-cutting) | Fact-checking chain; not a BaseAgent subclass |

**Active refactor:** `f_ui_template_agent` is being eliminated. Domain agents now produce the final FE payload directly via `OUTPUT_TEMPLATE` / `RESPONSE_FORMAT` on `BaseAgent`. See `docs/remove-ui-template-agent/` for the full plan.

### BaseAgent Key Attributes

```python
class MyAgent(BaseAgent):
    TOOL_TO_AF_MAP: dict[str, str] = {}        # tool_name → AF display name for agent_flow events
    RESPONSE_FORMAT: type[BaseModel] | None = None  # structured_response output schema
    OUTPUT_TEMPLATE: type[BaseModel] | None = None  # parse fenced JSON from token stream
```

- Set `RESPONSE_FORMAT` when the model supports native structured output.
- Set `OUTPUT_TEMPLATE` when the model should emit a fenced JSON block in its text; `BaseAgent.stream()` parses and validates it automatically.
- `LeadingAgent` uses `OUTPUT_TEMPLATE = QuickReplyDataEvent` (defined in `agents/templates/schemas.py`).

### LLM Instances (`router.py`)

| Variable | Model config | Used by |
|----------|-------------|---------|
| `REASONING_LLM` | `AI_MODEL_REASONING`, streaming | Leading, Discovery, Transaction, Support agents |
| `LLM` | `AI_MODEL`, streaming | UI Template agent (fast rendering) |
| `QC_LLM` | `AI_QC_MODEL`, temperature=0 | QC fact-check chain |

### Streaming Events

All events from `BaseAgent.stream()`:

| Event type | Key fields | Description |
|------------|-----------|-------------|
| `status` | `status` | Lifecycle: `"생각 중..."`, `"답변 중..."`, or `"tool_start"` (+ `tool`, `display_name`) |
| `token` | `content` | AI response text chunk |
| `message` | `content`, `node`, `agent` | Full agent message |
| `tool` | `input`, `output`, `node`, `tool` | Tool execution result |
| `agent_flow` | `agent`, `status` | AF name with `"success"` or `"error"` (from tool result JSON) |
| `data` | `template`, `data` | Final FE UI payload (emitted when structured output validated) |

### FE Template Schemas (`agents/templates/schemas.py`)

`TemplatePayload` → `DataEvent` → per-template classes (e.g., `QuickReplyTemplate`, `QuickReplyDataEvent`). These Pydantic models are the single source of truth for the FE contract. New templates must be defined here.

### QC Agent (`g_qc_agent/`)

Not a `BaseAgent` subclass. Implements a simple LangChain chain (`ChatPromptTemplate | LLM | StrOutputParser`). Invoked via `invoke_qc()` / `stream_qc()` to fact-check domain agent responses against raw tool output. Returns `"PASS"` or a corrected response string.

### External Integrations
| Service | Purpose |
|---------|---------|
| LiteLLM + Bedrock (via `AI_GATEWAY_BASE_URL`) | LLM gateway |
| Qdrant | Vector store (RAG) |
| Redis | Celery queue |
| Langfuse | Tracing/observability |
| Oracle | Product/customer data (via tstation-be) |

## Code Standards

- Line length: 120 chars
- Python 3.12, `uv` package manager
- kebab-case filenames, prefix ordering for agents (`a_`, `b_`, `c_`, ...)
- Files under 200 lines; split large modules
- Type hints required on parameters and return types
- See `docs/code-standards.md` for full details

## Key Paths
```
app/tstation-ai/services/tstation/agents/   # All agents
app/tstation-ai/services/tstation/agents/base_agent.py  # BaseAgent + TOOL_DISPLAY_NAMES
app/tstation-ai/services/tstation/agents/router.py      # LLM singletons + AgentDomain router
app/tstation-ai/services/tstation/agents/templates/     # FE schema models
app/tstation-be-openapi.json                # OpenAPI spec for API client generation
docs/remove-ui-template-agent/             # Active refactor plan docs
```

## Environment Variables
See `.env.example`:
- `ENV`: local|dev|stag|prod
- `AI_DEFAULT_PROVIDER`: LLM provider
- `AI_GATEWAY_BASE_URL` / `AI_GATEWAY_API_KEY`: LiteLLM gateway
- `AI_MODEL` / `AI_MODEL_REASONING` / `AI_QC_MODEL`: Model names per tier
- `REDIS_URL`: Queue connection
- `AWS_BEARER_TOKEN_BEDROCK`: Bedrock auth
