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
│  │              Agent Layer (Multi-Agent)                  │  │
│  │  ┌─────────────────────────────────────────────────┐   │  │
│  │  │         BaseAgent (Base Class)                   │   │  │
│  │  │  - Streaming support                              │   │  │
│  │  │  - TOOL_TO_AF_MAP                                │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  │        │    │    │    │                                 │  │
│  │        ▼    ▼    ▼    ▼                                 │  │
│  │  ┌───┐  ┌───┐  ┌───┐  ┌───┐  ┌───┐                   │  │
│  │  │ L │  │ D │  │ T │  │ S │  │ P │                   │  │
│  │  │ e │  │ i │  │ r │  │ h │  │ u │                   │  │
│  │  │ a │  │ s │  │ a │  │ o │  │ p │                   │  │
│  │  │ d │  │ c │  │ n │  │ p │  │ p │                   │  │
│  │  │ i │  │ o │  │ s │  │ i │  │ o │                   │  │
│  │  │ n │  │ v │  │ a │  │ n │  │ r │                   │  │
│  │  │ g │  │ e │  │ c │  │ t │  │ t │                   │  │
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

### BaseAgent (base_agent.py)

All agents inherit from the `BaseAgent` class which provides:

- **Streaming Support**: Yields agent flow events and tokens during execution
- **TOOL_TO_AF_MAP**: Dictionary mapping tool names to Agent Functions (AF)
- **Stream Event Types**:
  - `agent_flow`: Agent name or AF when active
  - `tokens`: AI response tokens
  - `message`: Agent messages with agent name
  - `tool`: Tool execution results

### Agent Flow Streaming Format

Agents emit `agent_flow` events in the following format:

```python
# Agent start event
{"type": "agent_flow", "agent": "[Discovery Agent]", "status": "success"}

# AF (Agent Function) execution event
{"type": "agent_flow", "agent": "[Product Compatibility AF]", "status": "success/error"}
```

Status is extracted from tool result: `"status": "success"` or `"status": "error"`

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

| Agent | Directory | BaseAgent | TOOL_TO_AF_MAP |
|-------|-----------|-----------|----------------|
| Leading | a_leading_agent/ | Yes | Yes |
| Discovery | b_discovery_agent/ | Yes | Yes |
| Transaction | c_transaction_agent/ | Yes | Yes |
| Shopping | d_shopping_agent/ | Yes | Yes |
| Support | e_support_agent/ | Yes | Yes |

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
