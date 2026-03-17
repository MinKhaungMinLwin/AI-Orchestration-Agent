# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

T-Station AI is an AI-powered service for Hankook Tire. It consists of three main components:

- **tstation-ai** (port 8000): Main AI service with FastAPI, LangChain agents, RAG (Qdrant), and task queue (Celery/Redis)
- **tstation-be** (port 8001): Backend service connecting to Oracle database
- **tstation-ui-demo** (port 7777): Streamlit-based demo UI

## Common Commands

### Development Setup
```bash
# Install Just (task runner)
curl -fsSL https://just.systems/install.sh | sudo bash -s -- --to /usr/local/bin

# Setup Python environment
just setup

# Activate virtual environment
source .venv/bin/activate
```

### Running Services
```bash
# Run AI service (port 8000)
set -a && source .env && set +a && uv run app/tstation-ai/main.py

# Run BE service (port 8001)
set -a && source app/tstation-be/.env && set +a && uv run app/tstation-be/main.py

# Run UI demo (port 7777)
uv run streamlit run app/tstation-ui-demo/Home.py --server.port 7777 --server.address 0.0.0.0
```

### Code Quality
```bash
just lint       # Check code with ruff
just fmt        # Format code with ruff + isort
```

### Docker Deployment
```bash
just start           # Start services with Docker (uses ENV=local by default)
just start-local     # Local development with Docker
just stop            # Stop Docker services
just start-remote    # Remote deployment with Docker (requires ENV=dev|stag|prod)
just stop-remote     # Stop remote Docker services
```

### Runway Deployment
```bash
just start-runway-ai      # Start AI service in Runway
just stop-runway-ai       # Stop AI service in Runway
just start-runway-be      # Start BE service in Runway
just stop-runway-be       # Stop BE service in Runway
just start-runway         # Start all services in Runway
just stop-runway         # Stop all services in Runway
```

## Architecture

### AI Agents (`app/tstation-ai/services/tstation/agents/`)
- **base_agent.py**: Base class with streaming support, TOOL_TO_AF_MAP for agent function mapping
- **a_leading_agent**: Primary orchestrator, domain routing
- **b_discovery_agent**: Product recommendations, compatibility checks
- **c_pricing_agent**: Price, stock, store inquiries
- **d_order_agent**: Purchase intent, quick order, order tracking
- **e_support_agent**: Warranty, returns, policies, FAQ
- **router.py**: Domain router that classifies and dispatches to appropriate agent

All agents inherit from `BaseAgent` which provides:
- `stream()` method yielding `agent_flow` events with agent name and tool status
- `TOOL_TO_AF_MAP` dict mapping tool names to AF (Agent Function) labels
- Status extracted from tool result (`success` or `error`)

### Domain Classification
| Domain | Agent | Description |
|--------|-------|-------------|
| LEADING | LeadingAgent | General/unclear queries |
| DISCOVERY | DiscoveryAgent | Product research, recommendations, compatibility |
| PRICING | TransactionAgent | Price, stock, store inquiries |
| ORDER | OrderAgent | Purchase intent, quick order |
| SUPPORT | SupportAgent | Warranty, returns, policies |

### Streaming Response
Stream yields events for UI display:
- `agent_flow`: `{"type": "agent_flow", "agent": "[Discovery Agent]", "status": "success/error"}`
- `token`: AI response tokens
- `tool`: Tool execution results

### Key Dependencies
- **FastAPI** + Uvicorn for API
- **LangChain** for AI/LLM agents
- **Qdrant** for vector storage (RAG)
- **Celery** + Redis for async task queue
- **Langfuse** for tracing/observability
- **LiteLLM** with Bedrock Claude Haiku 4.5

### Configuration
Environment variables in `.env` (see `.env.example`):
- `ENV`: Environment mode (`local`, `dev`, `staging`, `prod`)
- `AI_DEFAULT_PROVIDER`: LLM provider (default: `openai`)
- `REDIS_URL`: Redis connection for queue
- `AWS_BEARER_TOKEN_BEDROCK`: AWS Bedrock authentication

Python 3.12 required. Package management via `uv` (see `pyproject.toml`).

## Code Standards

- Line length: 120 characters
- Python 3.12 target
- Use ruff for linting/formatting
- Use isort for import sorting
- Agent directories use prefix ordering (a_, b_, c_, etc.)

## Project Structure

```
app/
├── tstation-ai/           # Main AI service
│   ├── api/               # API endpoints
│   ├── agents/            # AI agents
│   ├── config/            # Configuration
│   ├── services/          # Business logic
│   └── main.py            # Application entry
├── tstation-be/           # Backend service (Oracle DB)
│   ├── app/routers/       # API routers
│   └── main.py            # Application entry
└── tstation-ui-demo/      # Demo UI
    └── Home.py            # Streamlit app

docs/
├── system-architecture.md
├── code-standards.md
├── project-overview-pdr.md
├── codebase-summary.md
└── project-roadmap.md
```
