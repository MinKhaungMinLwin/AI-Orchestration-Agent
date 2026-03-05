# T-Station AI Codebase Summary

## Overview

This document provides a summary of the T-Station AI codebase structure, generated from the repomix compaction. The project consists of three main components with a total of approximately 150,000 tokens across 76 files.

## Repository Structure

```
tstation-ai/
├── api/                        # API endpoints
│   ├── tstation/
│   │   ├── chat.py            # Main chat endpoint
│   │   └── example_question.py
│   ├── monitoring.py          # Health check, metrics
│   ├── queue.py               # Queue system endpoints
│   └── router.py              # Main router (environment-based)
├── common/                     # Shared utilities
│   ├── curr_time.py           # Timezone-aware time
│   ├── detect_language.py     # Language detection
│   ├── openai.py              # OpenAI client
│   └── s3.py                  # S3 utilities
├── config/                     # Configuration
│   ├── env.py                 # Environment settings
│   ├── log.py                 # Logging configuration
│   ├── sec.py                 # Security (API keys)
│   └── tracing.py              # Tracing setup
├── schemas/                    # Pydantic models
│   ├── tstation/
│   │   ├── chat.py
│   │   └── example_question.py
│   └── queue.py
├── services/
│   └── tstation/
│       ├── agents/            # AI Agents
│       │   ├── a_leading_agent/
│       │   │   └── agent.py
│       │   ├── b_discovery_agent/
│       │   │   ├── agent.py
│       │   │   └── tools.py
│       │   ├── faq_agent/     # RAG-based FAQ
│       │   │   ├── config/
│       │   │   ├── faq/
│       │   │   ├── scripts/
│       │   │   ├── share/
│       │   │   └── requirements.txt
│       │   ├── store_agent/
│       │   │   └── store_af.py
│       │   └── router.py      # Domain router
│       ├── chat.py            # Chat service
│       └── example_question.py
├── static/                     # Static files
│   └── files/example_questions/
├── main.py                    # Application entry
├── celery_app.py              # Celery configuration
└── requirements.txt

tstation-be/                    # Backend service
├── app/
│   ├── routers/               # API routers
│   │   ├── compatibility.py
│   │   ├── description.py
│   │   ├── escalation.py
│   │   ├── faq.py
│   │   ├── inventory.py
│   │   ├── order.py
│   │   ├── price.py
│   │   ├── quick_order.py
│   │   ├── recommendation.py
│   │   └── shop.py
│   ├── database.py
│   └── schemas.py
├── tests/                     # Test files
├── main.py
└── pyproject.toml

tstation-ui-demo/               # Demo UI
├── api/chat.py
├── Home.py
└── requirements.txt
```

## Top Files by Token Count

| File | Tokens | Description |
|------|--------|-------------|
| tstation-ai/requirements.txt | 81,107 | Python dependencies |
| tstation-ui-demo/requirements.txt | 21,288 | UI dependencies |
| b_discovery_agent/tools.py | 3,400 | Discovery agent tools |
| tstation-be/app/schemas.py | 2,520 | Backend schemas |
| faq_agent/scripts/load_sample_reviews.py | 1,672 | FAQ loading script |

## Key Components

### AI Agents (`app/tstation-ai/services/tstation/agents/`)

1. **Leading Agent** (`a_leading_agent/agent.py`)
   - Central orchestrator
   - Routes queries to sub-agents
   - Entry point for all chat requests

2. **Discovery Agent** (`b_discovery_agent/`)
   - Product recommendations
   - Compatibility checks
   - Product descriptions
   - Tools: price lookup, inventory check, description generation

3. **FAQ Agent** (`faq_agent/`)
   - RAG-based policy inquiries
   - Qdrant vector store for retrieval
   - OpenAI integration for generation
   - Scripts for loading FAQs to vector store

4. **Store Agent** (`store_agent/store_af.py`)
   - Store integration
   - In development

### Backend Routers (`app/tstation-be/app/routers/`)

| Router | Purpose |
|--------|---------|
| `shop.py` | Shop information |
| `price.py` | Tire pricing |
| `inventory.py` | Stock availability |
| `recommendation.py` | Product recommendations |
| `order.py` | Order management |
| `quick_order.py` | Quick ordering |
| `compatibility.py` | Tire-vehicle compatibility |
| `description.py` | Product descriptions |
| `faq.py` | FAQ data |
| `escalation.py` | Human escalation |

## Configuration

### Environment Variables (`.env`)

```env
# Application
ENV=dev                    # local, dev, staging, prod
PROJECT_NAME=tstation-ai
API_SECRET_KEY=ADD_KEY

# AI
AI_DEFAULT_PROVIDER=openai
AWS_BEARER_TOKEN_BEDROCK=ADD_KEY

# Queue
REDIS_URL=redis://...

# AWS
AWS_DEFAULT_REGION=ap-northeast-2
S3_BUCKET_NAME=ADD_KEY

# Monitoring
LANGFUSE_SECRET_KEY=ADD_KEY
```

### Environment Modes

- **LOCAL**: Local development
- **DEV**: Development server
- **STAGING**: Staging environment
- **PROD**: Production environment

## Dependencies

### Main Application
- fastapi, uvicorn
- langchain, langchain-openai
- qdrant-client
- celery, redis
- langfuse

### Backend
- fastapi
- oracledb
- sqlalchemy

### UI Demo
- streamlit
- requests

## API Endpoints

### T-Station AI (`/tstation`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/tstation/chat` | POST | Main chat endpoint |
| `/tstation/chat/example_questions/{language}` | GET | Get example questions |

### Monitoring (`/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/test/success` | GET | Test endpoint |
| `/test/raise-error` | POST | Error test |
| `/metrics` | GET | Prometheus metrics |

## Development Notes

- Python 3.12 required
- Use `uv` for package management
- Use `ruff` for linting/formatting
- Agent directories use prefix ordering (a_, b_, etc.) for import order
