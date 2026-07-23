# T-Station AI System Architecture

## Overview

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea using the Chat V3 LLM-first runtime with
FastAPI. The system handles customer inquiries about tires, providing product recommendations, compatibility checks,
store information, reservation, ordering, and support.

The active agent/runtime entrypoint is `app/tstation-ai/services/tstation/chat_v3/` (`/chat_v3`). Before changing
runtime behavior, read `docs/chat-v3/MIGRATE_V2_TO_V3_EN.md`.

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| tstation-ai | 9000 | Main AI service (FastAPI) |
| tstation-be | 8000 | Backend service (Oracle DB) |

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
│                    (FastAPI, Port 9000)                      │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                     API Layer                          │  │
│  │   POST /tstation/chat   GET /tstation/example_questions│  │
│  │   GET /health   GET /metrics                          │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                                │
│                              ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Service Layer                              │  │
│  │   TStationChatServiceV3 (chat_v3/service.py)           │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                                │
│                              ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Chat V3 Runtime                            │  │
│  │                                                         │  │
│  │  router/           — Guard, domain, intent, tool plan   │  │
│  │  executor.py       — Tool loop over shared tools         │  │
│  │  templates.py      — Tool output → FE templates          │  │
│  │  composer.py       — assistantResponse + quick replies   │  │
│  │  qc.py             — Verification                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                                │
│                              ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              External Services                         │  │
│  │   LiteLLM AI Gateway (GPT-5.4 / GPT-4o-mini)          │  │
│  │   Qdrant (RAG)   Langfuse (tracing)   Redis (history)  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    T-Station Backend                         │
│                    (FastAPI, Port 8000)                      │
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

## Chat V3 Architecture

### Runtime Components

| Component | Path | Responsibility |
|-----------|------|----------------|
| Service | `services/tstation/chat_v3/service.py` | Current orchestration entrypoint |
| Router | `services/tstation/chat_v3/router/` | LLM-first safety, guard, domain, intent, slot, tool decision |
| Executor | `services/tstation/chat_v3/executor.py` | Executes shared tools |
| Templates | `services/tstation/chat_v3/templates.py` | Builds FE template payloads |
| Composer/QC | `services/tstation/chat_v3/composer.py`, `services/tstation/chat_v3/qc.py` | Final response and verification |
| SSE | `services/tstation/chat_v3/sse.py` | FE-compatible stream events |

### Domain Classification

Routes queries through `chat_v3/router` into one or more domains:

| Domain | Agent | Description |
|--------|-------|-------------|
| LEADING | V3 guard/composer or shared leading behavior | Greeting, unclear intent, small talk |
| DISCOVERY | Shared discovery tools | Product search, recommendations, compatibility |
| TRANSACTION | Shared transaction tools | Price, stock, stores, booking, orders, cart |
| SUPPORT | Shared support tools | Warranty, returns, FAQ, human escalation |

### Shared Legacy Agent Surfaces

`services/tstation/agents/` is not the current root runtime. V3 reuses `agents/*/tools.py` and
`agents/templates/schemas.py` as shared tool/schema surfaces. Legacy V2 agent classes remain there for compatibility.

### LLM Models

| Variable | Model | Usage |
|----------|-------|-------|
| AI_MODEL | gpt-5.4 | Main response/composition tier |
| AI_MODEL_MINI | provider default | V3 router and lightweight structured decisions |
| AI_MODEL_REASONING | gpt-5.4-reasoning | Reasoning tier where configured |
| AI_QC_MODEL | gpt-4o-mini | QC tier |

### Chat V3 Flow

```
User message
    → TStationChatServiceV2.chat() branch gate
    → TStationChatServiceV3.chat()
    → chat_v3/router route decision
    → chat_v3/executor shared tool loop
    → chat_v3/templates / composer / qc
    → chat_v3/sse final SSE stream to FE
```

### QC

Current QC behavior starts in `chat_v3/qc.py`. Legacy `g_qc_agent/` remains a compatibility/shared implementation.

## State Management (Redis)

| Key type | Content |
|----------|---------|
| Chat history | Full conversation messages per session |
| Slots | Extracted intents: goods_no, tire_size, shop_id, quantity |
| Tool context | Last tool outputs for cross-turn context |
| Template data | UI card data attached to assistant messages |

## Backend Routers (tstation-be)

| Router | Purpose |
|--------|---------|
| shop.py | Store list, detail, schedule |
| price.py | Final price, coupons, discount compare |
| inventory.py | Logistics & store stock |
| recommendation.py | Product recommendations |
| order.py | Order list, order tracking |
| quick_order.py | Quick order form |
| compatibility.py | Tire-vehicle compatibility |
| description.py | Product descriptions |
| faq.py | FAQ data |
| escalation.py | Human agent escalation |

## External Integrations

| Service | Purpose | Provider |
|---------|---------|----------|
| OpenAI GPT-5.4 | Main LLM for agents | OpenAI via LiteLLM |
| OpenAI GPT-4o-mini | QC Agent LLM | OpenAI via LiteLLM |
| Qdrant | Vector store for FAQ RAG | Qdrant |
| Langfuse | Tracing and observability | Langfuse |
| Redis | Conversation history, slots, tool context | Redis |
| Oracle | Product/customer data | Oracle |

## Monitoring

- Health checks: GET /health
- Metrics: GET /metrics (Prometheus)
- Tracing: Langfuse integration (all agent runs traced)

## Security

- API key authentication via `API_SECRET_KEY`
- JWT token for tstation-be API calls
- PII guardrail check before processing
- Environment-based configuration (LOCAL/DEV/STAGING/PROD)
