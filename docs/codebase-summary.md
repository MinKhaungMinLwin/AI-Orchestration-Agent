# T-Station AI Codebase Summary

## Overview

This document provides a summary of the T-Station AI codebase structure. The project consists of three main components.

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| tstation-ai | 8000 | Main AI service |
| tstation-be | 8001 | Backend service |
| tstation-ui-demo | 7777 | Demo UI |

## Repository Structure

```
tstation-ai/
├── app/
│   ├── tstation-ai/              # Main AI service
│   │   ├── api/                  # API endpoints
│   │   │   ├── monitoring.py     # Health, metrics
│   │   │   ├── router.py         # Main router
│   │   │   └── tstation/        # Chat endpoints
│   │   ├── common/               # Shared utilities
│   │   ├── config/               # Configuration
│   │   ├── schemas/              # Pydantic models
│   │   ├── services/
│   │   │   └── tstation/
│   │   │       ├── agents/      # AI Agents
│   │   │       │   ├── a_leading_agent/
│   │   │       │   ├── b_discovery_agent/
│   │   │       │   ├── c_transaction_agent/
│   │   │       │   ├── d_shopping_agent/
│   │   │       │   ├── e_support_agent/
│   │   │       │   └── router.py
│   │   │       └── chat.py
│   │   └── main.py              # Entry point
│   ├── tstation-be/             # Backend service
│   │   ├── app/routers/        # API routers
│   │   └── main.py
│   └── tstation-ui-demo/        # Demo UI
│       └── Home.py
├── docs/                        # Documentation
└── pyproject.toml
```

## AI Agents

| Agent | Directory | Purpose |
|-------|-----------|---------|
| Leading | a_leading_agent/ | Orchestrator, domain classification |
| Discovery | b_discovery_agent/ | Product recommendations, compatibility |
| Transaction | c_transaction_agent/ | Purchase intent, orders |
| Shopping | d_shopping_agent/ | Price, stock, store |
| Support | e_support_agent/ | Policies, warranty, FAQ |

## Key Dependencies

### tstation-ai
- fastapi, uvicorn
- langchain, langchain-litellm
- qdrant-client
- celery, redis
- langfuse

### tstation-be
- fastapi
- oracledb
- sqlalchemy

### tstation-ui-demo
- streamlit
- requests

## API Endpoints

### T-Station AI
- POST /tstation/chat - Main chat endpoint
- GET /tstation/chat/example_questions/{language} - Example questions

### Monitoring
- GET /health - Health check
- GET /metrics - Prometheus metrics

## Configuration

Environment variables in `.env`:
- ENV (local, dev, staging, prod)
- AI_DEFAULT_PROVIDER
- REDIS_URL
- AWS_BEARER_TOKEN_BEDROCK

## Development

- Python 3.12
- Package manager: uv
- Linting: ruff
- Task runner: just
