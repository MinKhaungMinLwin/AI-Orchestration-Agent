# T-Station AI System Architecture

## Overview

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea using a multi-agent architecture with FastAPI. The system handles customer inquiries about tires, providing product recommendations, compatibility checks, store information, reservation, ordering, and support.

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| tstation-ai | 9000 | Main AI service (FastAPI) |
| tstation-be | 8000 | Backend service (Oracle DB) |
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
│  │   TStationChatService (StreamingMultiAgentCoordinator) │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                                │
│                              ▼                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Agent Layer (Multi-Agent)                  │  │
│  │                                                         │  │
│  │  a_leading_agent    — Greeting, unclear intent          │  │
│  │  b_discovery_agent  — Product search, recommendations   │  │
│  │  c_transaction_agent— Price, store, booking, orders     │  │
│  │  e_support_agent    — FAQ, warranty, escalation (RAG)   │  │
│  │  f_ui_template_agent— UI template rendering             │  │
│  │  g_qc_agent         — Fact-check (currently DISABLED)   │  │
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

## Agent Architecture

### BaseAgent (base_agent.py)

All agents inherit from the `BaseAgent` class which provides:

- **Streaming Support**: Yields structured events during execution
- **TOOL_TO_AF_MAP**: Dictionary mapping tool names to Agent Functions (AF)
- **OUTPUT_TEMPLATE**: Optional structured output template (e.g. `ProductDataEvent`)
- **Stream Event Types**:
  - `status`: Lifecycle markers — "생각 중...", "답변 중..."
  - `agent_flow`: Agent name or AF when active
  - `token`: AI response tokens
  - `message`: Agent messages with agent name (held for history sync)
  - `tool_start`: Before tool runs, with display_name for UI indicator
  - `tool`: Tool execution results with name, input, output
  - `data`: Final UI template payload (structured response)

### Domain Classification

Routes queries to appropriate agents via `StreamingMultiAgentCoordinator`:

| Domain | Agent | Description |
|--------|-------|-------------|
| LEADING | a_leading_agent | Greeting, unclear intent, small talk |
| DISCOVERY | b_discovery_agent | Product search, recommendations, compatibility |
| TRANSACTION | c_transaction_agent | Price, stock, stores, booking, orders, cart |
| SUPPORT | e_support_agent | Warranty, returns, FAQ, human escalation |

### Agent Details

| Agent | Model | Tools |
|-------|-------|-------|
| a_leading_agent | GPT-5.4-reasoning | None (pure LLM) |
| b_discovery_agent | GPT-5.4-reasoning | search_product, get_recommendations, check_compatibility, get_final_price, get_events, get_deals, compare_discount, search_youtube |
| c_transaction_agent | GPT-5.4-reasoning | get_final_price, get_store_list, get_store_detail, get_store_schedule, quick_order, save_to_cart, get_order_status, get_orders_of_user |
| e_support_agent | GPT-5.4-reasoning | get_faq, search_faq_rag, escalate |
| f_ui_template_agent | GPT-5.4 | UI template tools (list_product, list_location, available_dates, preorder, etc.) |
| g_qc_agent | GPT-4o-mini | No tools — LLM chain (currently DISABLED) |

### LLM Models

| Variable | Model | Usage |
|----------|-------|-------|
| AI_MODEL | gpt-5.4 | UI Template Agent, router classification |
| AI_MODEL_REASONING | gpt-5.4-reasoning | All main sub-agents |
| AI_QC_MODEL | gpt-4o-mini | QC Agent (disabled) |

### Multi-Agent Coordinator Flow

```
User message
    → classify_multi_intent() [GPT-5.4]
    → inject CONVERSATION CONTEXT
    → route to agent(s)
    → after each agent: decide_next_action() STOP or CONTINUE
    → (optional) f_ui_template_agent for UI card rendering
    → local _sanitize_response()
    → yield final SSE stream to FE
```

### QC Agent (g_qc_agent) — Currently DISABLED

The QC agent exists but is disabled in `chat.py`. When enabled, it:
- Runs after all agents complete
- Only for responses with factual claims (price, goods_no, store names, tire sizes)
- Compares draft response vs tool source data
- Returns PASS or corrected response

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
