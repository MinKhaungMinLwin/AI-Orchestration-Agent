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
just start              # Start services with Docker (ENV=local by default)
just stop               # Stop Docker services
ENV=dev just start      # Remote deployment (dev|stag|prod)
```

### Runway (No Docker)
```bash
just start-runway       # Start all 3 services in background
just stop-runway        # Stop all uv processes
```

## Architecture

### Agent Structure (`app/tstation-ai/services/tstation/agents/`)
Each agent inherits `BaseAgent` providing `stream()` and `TOOL_TO_AF_MAP`.

| Prefix | Agent | Domain | Description |
|--------|-------|--------|-------------|
| a_ | leading_agent | LEADING | Primary orchestrator, domain routing |
| b_ | discovery_agent | DISCOVERY | Product recommendations, compatibility |
| c_ | transaction_agent | TRANSACTION | Orders, purchase intent |
| e_ | support_agent | SUPPORT | Warranty, returns, policies |

### Streaming Events
```python
{"type": "agent_flow", "agent": "[Agent Name]", "status": "success|error"}
{"type": "token", "content": "..."}
{"type": "tool", "content": "...", "node": "...", "tool": "..."}
```

### External Integrations
| Service | Purpose |
|---------|---------|
| LiteLLM + Bedrock Claude Haiku 4.5 | LLM |
| Qdrant | Vector store (RAG) |
| Redis | Celery queue |
| Langfuse | Tracing/observability |
| Oracle | Product/customer data |

## Code Standards

- Line length: 120 chars
- Python 3.12, `uv` package manager
- kebab-case filenames, prefix ordering for agents (a_, b_, c_, ...)
- Files under 200 lines; split large modules
- See `docs/code-standards.md` for full details

## Key Paths
```
app/tstation-ai/           # AI service (agents, api, config, services)
app/tstation-be/           # Backend service (Oracle DB)
app/tstation-ui-demo/      # Streamlit demo UI
app/tstation-be-openapi.json  # OpenAPI spec for API client generation
docker/                    # Remote docker-compose
docker_local/              # Local docker-compose
docs/                      # Architecture, standards, roadmap
```

## Environment Variables
See `.env.example`:
- `ENV`: local|dev|stag|prod
- `AI_DEFAULT_PROVIDER`: LLM provider
- `REDIS_URL`: Queue connection
- `AWS_BEARER_TOKEN_BEDROCK`: Bedrock auth
