# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea using a Chat V3 LLM-first FastAPI runtime.

## Current Agent Runtime

The active agent/runtime entrypoint is `app/tstation-ai/services/tstation/chat_v3/` (`/chat_v3` in shorthand).
Before changing routing, tool execution, templates, QC, or SSE behavior, read
`docs/chat-v3/MIGRATE_V2_TO_V3_EN.md`.

`services/tstation/chat.py` and `services/tstation/agents/` are legacy V2 compatibility and shared tool/schema
surfaces. Do not treat them as the root runtime unless you are explicitly working on legacy V2 compatibility or a
shared tool/schema used by V3.

### Services
| Service | Port | Description |
|---------|------|-------------|
| tstation-ai | 9000 | Main AI service (FastAPI) with Chat V3 runtime, shared tools, RAG (Qdrant), Celery/Redis |
| tstation-be | 8000 | Backend service connecting to Oracle database |

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

### Chat V3 Structure (`app/tstation-ai/services/tstation/chat_v3/`)

V3 owns routing, tool-loop execution, response composition, template creation, QC, and SSE emission. The migration
and runtime guide is `docs/chat-v3/MIGRATE_V2_TO_V3_EN.md`.

| Area | Path | Description |
|------|------|-------------|
| Service | `chat_v3/service.py` | Single V3 orchestration entrypoint |
| Router | `chat_v3/router/` | LLM-first safety, guard, domain, intent, slot, tool decision |
| Executor | `chat_v3/executor.py` | Tool loop over reused domain tools |
| Templates | `chat_v3/templates.py` | Tool output to FE template payloads |
| Composer/QC | `chat_v3/composer.py`, `chat_v3/qc.py` | Assistant response and verification |

### Shared Legacy Agent Surfaces (`app/tstation-ai/services/tstation/agents/`)

The V2 agent folders are not the current root runtime. V3 reuses their tools and FE schema contracts where needed.

| Prefix | Agent | Domain | Description |
|--------|-------|--------|-------------|
| a_ | leading_agent | LEADING | Legacy V2 leading agent |
| b_ | discovery_agent | DISCOVERY | Product recommendation, compatibility, vehicle lookup tools reused by V3 |
| c_ | transaction_agent | TRANSACTION | Order, pricing, stock, store search tools reused by V3 |
| e_ | support_agent | SUPPORT | Warranty, return, FAQ, 1:1 escalation tools reused by V3 |
| f_ | ui_template_agent | (legacy) | Legacy V2 UI formatting; V3 uses `chat_v3/templates.py` |
| g_ | qc_agent | (shared/legacy) | Fact-checking implementation reused or mirrored by V3 QC |

For current V3 migration status, TODOs, and operational flags, use `docs/chat-v3/MIGRATE_V2_TO_V3_EN.md`.

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

### LLM Instances

V3 routing and composition live under `chat_v3/` and use the model tiers configured in `.env` (`AI_MODEL`,
`AI_MODEL_MINI`, `AI_QC_MODEL`, and provider settings). Legacy `agents/router.py` may still define V2 singletons,
but it is not the V3 root router.

### Streaming Events

V3 emits the FE-compatible SSE contract from `chat_v3/sse.py` and related composer/template code:

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

### QC

Current QC behavior starts in `chat_v3/qc.py`. Legacy `g_qc_agent/` remains available as a shared/compatibility
implementation, but new V3 QC behavior should be added in the V3 owner layer.

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
app/tstation-ai/services/tstation/chat_v3/  # Current agent/runtime entrypoint
app/tstation-ai/services/tstation/chat_v3/service.py  # V3 orchestration entrypoint
app/tstation-ai/services/tstation/chat_v3/router/     # V3 LLM-first router
app/tstation-ai/services/tstation/agents/   # Shared tools/schema + legacy V2 agents
app/tstation-ai/services/tstation/agents/templates/     # FE schema models shared by V2/V3
app/tstation-be-openapi.json                # OpenAPI spec for API client generation
docs/chat-v3/MIGRATE_V2_TO_V3_EN.md        # V3 migration/runtime guide
```

## Environment Variables
See `.env.example`:
- `ENV`: local|dev|stag|prod
- `AI_DEFAULT_PROVIDER`: LLM provider
- `AI_GATEWAY_BASE_URL` / `AI_GATEWAY_API_KEY`: LiteLLM gateway
- `AI_MODEL` / `AI_MODEL_REASONING` / `AI_QC_MODEL`: Model names per tier
- `REDIS_URL`: Queue connection
- `AWS_BEARER_TOKEN_BEDROCK`: Bedrock auth
