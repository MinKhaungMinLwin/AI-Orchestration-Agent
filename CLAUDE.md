# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

T-Station AI is an AI-powered service for Hankook Tire. It consists of three main components:

- **tstation-ai** (port 9000): Main AI service with FastAPI, LangChain agents, RAG (Qdrant), and task queue (Celery/Redis)
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
# Run AI service (port 9000)
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
just start      # Start services with Docker
just stop       # Stop Docker services
just start-local   # Local development with Docker
```

## Architecture

### AI Agents (`app/tstation-ai/services/tstation/agents/`)
- **a_leading_agent**: Primary agent that routes requests
- **b_discovery_agent**: Discovery agent
- **faq_agent**: FAQ retrieval using RAG (Qdrant vector store)
- **store_agent**: Store-related agent
- **router.py**: Domain router that dispatches to appropriate agent

### Key Dependencies
- FastAPI + Uvicorn for API
- LangChain for AI/LLM agents
- Qdrant for vector storage (RAG)
- Celery + Redis for async task queue
- Langfuse for tracing/observability
- OpenAI API for LLM

### Configuration
- Environment variables in `.env` (see `.env.example`)
- Settings in `app/tstation-ai/config/env.py`
- Python 3.12 required
- Package management via `uv` (see `pyproject.toml`)

## Code Standards

- Line length: 120 characters
- Python 3.12 target
- Use ruff for linting/formatting
- Use isort for import sorting
- Agent directories use prefix ordering (a_leading_, b_discovery_, etc.)



## AI Agents

The system uses a multi-agent architecture with domain routing:

| Agent | Purpose |
|-------|---------|
| **Leading Agent** | Central orchestrator, routes to sub-agents |
| **Discovery Agent** | Product recommendations, compatibility checks, descriptions |
| **FAQ Agent** | RAG-based policy inquiries using Qdrant + OpenAI |
| **Store Agent** | Store integration (in development) |

### Domain Classification

| Domain | Description |
|--------|-------------|
| LEADING | General/unclear queries |
| DISCOVERY | Product research, recommendations, compatibility |
| SHOPPING | Price, stock, store inquiries |
| TRANSACTION | Purchase intent |
| SUPPORT | Warranty, returns, policies |

## Key Dependencies

- **FastAPI** + Uvicorn for API
- **LangChain** for AI/LLM agents
- **Qdrant** for vector storage (RAG)
- **Celery** + Redis for async task queue
- **Langfuse** for tracing/observability
- **LiteLLM** with Bedrock Claude Haiku 4.5

## Configuration

Environment variables are defined in `.env` (see `.env.example`):

- `ENV`: Environment mode (`local`, `dev`, `staging`, `prod`)
- `AI_DEFAULT_PROVIDER`: LLM provider (default: `openai`)
- `REDIS_URL`: Redis connection for queue
- `AWS_BEARER_TOKEN_BEDROCK`: AWS Bedrock authentication

## Project Structure

```
app/
├── tstation-ai/           # Main AI service
│   ├── api/               # API endpoints
│   ├── agents/            # AI agents
│   ├── config/            # Configuration
│   ├── services/          # Business logic
│   └── main.py            # Application entry
├── tstation-be/           # Backend service
│   ├── app/routers/       # API routers
│   └── main.py            # Application entry
└── tstation-ui-demo/      # Demo UI
    └── Home.py            # Streamlit app
```

## Documentation

- [System Architecture](./docs/system-architecture.md)
- [Code Standards](./docs/code-standards.md)
- [Project Overview & PDR](./docs/project-overview-pdr.md)
- [Codebase Summary](./docs/codebase-summary.md)
- [Project Roadmap](./docs/project-roadmap.md)
