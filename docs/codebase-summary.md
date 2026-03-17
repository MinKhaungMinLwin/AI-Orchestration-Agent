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
│   │   │       │   ├── base_agent.py      # Base class
│   │   │       │   ├── a_leading_agent/
│   │   │       │   ├── b_discovery_agent/
│   │   │       │   ├── c_transaction_agent/
│   │   │       │   ├── d_order_agent/
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

### BaseAgent (base_agent.py)

All agents inherit from the `BaseAgent` class:

```python
class BaseAgent(ABC):
    TOOL_TO_AF_MAP: dict[str, str] = {}  # Tool to Agent Function mapping

    def __init__(self, model, tools, system_prompt, name):
        ...

    def stream(self, messages: list[dict]):
        # Yields agent_flow, token, message, tool events
        ...
```

### Agent Classes

| Agent | Directory | AF (Agent Functions) |
|-------|-----------|---------------------|
| Leading | a_leading_agent/ | Orchestrator |
| Discovery | b_discovery_agent/ | Product Compatibility, Product Recommendation, Product Description |
| Transaction | c_transaction_agent/ | Purchase intent handling |
| Order | d_order_agent/ | Order management |
| Support | e_support_agent/ | Policies, warranty, FAQ |

### Agent Flow Streaming

The streaming API yields events:

```python
# Agent start
{"type": "agent_flow", "agent": "[Discovery Agent]", "status": "success"}

# Agent Function execution
{"type": "agent_flow", "agent": "[Product Compatibility AF]", "status": "success/error"}

# Token
{"type": "token", "content": "..."}

# Tool result
{"type": "tool", "content": "...", "tool": "tool_name"}
```

### TOOL_TO_AF_MAP Example (Discovery Agent)

```python
TOOL_TO_AF_MAP = {
    "get_compatibility_tool": "Product Compatibility",
    "post_vehicle_verify_owner_tool": "Product Compatibility",
    "get_compatible_product_tool": "Product Compatibility",
    "get_user_vehicles_tool": "Product Compatibility",
    "get_products_recommendations_tool": "Product Recommendation",
    "get_product_description_tool": "Product Description",
}
```

## Streamlit UI (tstation-ui-demo)

The demo UI displays agent flow at the top of chat:

- Each step shown as colored badge (green for success, red for error)
- Steps connected with arrows
- Left-aligned with flexbox

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
- POST /tstation/chat - Main chat endpoint (supports streaming)
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
