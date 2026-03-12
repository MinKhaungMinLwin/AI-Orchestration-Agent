# T-Station AI System Architecture

## Overview

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea using a multi-agent architecture with FastAPI. The system handles customer inquiries about tires, providing product recommendations, compatibility checks, store information, and support.

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| tstation-ai | 8000 | Main AI service (FastAPI) |
| tstation-be | 8001 | Backend service (Oracle DB) |
| tstation-ui-demo | 7777 | Streamlit demo UI |

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Applications                      │
│    Web UI / Mobile App / LINE API / Other Integrations      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    T-Station AI Service                      │
│                    (FastAPI, Port 8000)                     │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                     API Layer                           │  │
│  │   POST /tstation/chat   GET /tstation/example_questions│  │
│  │   GET /health   GET /metrics                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                                │
│                              ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Service Layer                              │  │
│  │   TStationChatService   ExampleQuestionsService       │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                                │
│                              ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Agent Layer (Multi-Agent)                 │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │              Domain Router (router.py)           │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  │        │    │    │    │                                │  │
│  │        ▼    ▼    ▼    ▼                                │  │
│  │  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐                   │  │
│  │  │ L │  │ D │  │ T │  │ S │  │ P │                   │  │
│  │  │ e │  │ i │  │ r │  │ h │  │ u │                   │  │
│  │  │ a │  │ s │  │ a │  │ o │  │ p │                   │  │
│  │  │ d │  │ c │  │ n │  │ p │  │ p │                   │  │
│  │  │ i │  │ o │  │ s │  │ p │  │ o │                   │  │
│  │  │ n │  │ v │  │ a │  │ i │  │ r │                   │  │
│  │  │ g │  │ e │  │ c │  │ n │  │ t │                   │  │
│  │  └───┘  └───┘  └───┘  └───┘  └───┘                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                                │
│                              ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              External Services                         │  │
│  │   LiteLLM/Bedrock   Qdrant   Langfuse   Redis        │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    T-Station Backend                         │
│                    (FastAPI, Port 8001)                      │
│    Shop | Price | Inventory | Recommendation | Order        │
│    QuickOrder | Compatibility | Description | FAQ           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Oracle Database                           │
│    Product Catalog | Pricing | Inventory | Customer Data    │
└─────────────────────────────────────────────────────────────┘
```

## Agent Architecture

### Domain Classification

Routes queries to appropriate agents:

| Domain | Agent | Description |
|--------|-------|-------------|
| LEADING | a_leading_agent | General/unclear queries |
| DISCOVERY | b_discovery_agent | Product research, recommendations, compatibility |
| TRANSACTION | c_transaction_agent | Purchase intent, orders |
| SHOPPING | d_shopping_agent | Price, stock, store inquiries |
| SUPPORT | e_support_agent | Warranty, returns, policies |

### Agent Details

| Agent | Directory | Status |
|-------|-----------|--------|
| Leading | a_leading_agent/ | Complete |
| Discovery | b_discovery_agent/ | Complete |
| Transaction | c_transaction_agent/ | Partial |
| Shopping | d_shopping_agent/ | Partial |
| Support | e_support_agent/ | Partial |

## Backend Routers

| Router | Purpose |
|--------|---------|
| shop.py | Store information |
| price.py | Tire pricing |
| inventory.py | Stock availability |
| recommendation.py | Product recommendations |
| order.py | Order management |
| quick_order.py | Quick ordering |
| compatibility.py | Tire-vehicle compatibility |
| description.py | Product descriptions |
| faq.py | FAQ data |
| escalation.py | Human escalation |

## External Integrations

| Service | Purpose | Provider |
|---------|---------|----------|
| Bedrock Claude Haiku 4.5 | LLM for AI responses | AWS |
| Qdrant | Vector store for RAG | Qdrant |
| Langfuse | Tracing and observability | Langfuse |
| Redis | Queue system | Redis |
| Oracle | Product/customer data | Oracle |

## Monitoring

- Health checks: GET /health
- Metrics: GET /metrics (Prometheus)
- Tracing: Langfuse integration

## Security

- API key authentication via API_SECRET_KEY
- Environment-based configuration (LOCAL/DEV/STAGING/PROD)
