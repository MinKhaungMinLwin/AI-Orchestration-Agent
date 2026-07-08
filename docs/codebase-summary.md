# T-Station AI Codebase Summary

## Overview

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea. The current agent runtime is Chat V3,
an LLM-first FastAPI flow under `app/tstation-ai/services/tstation/chat_v3/`, streaming SSE responses to frontend.
Before runtime work, read `docs/chat-v3/MIGRATE_V2_TO_V3_EN.md`.

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| tstation-ai | 9000 | Main AI service |
| tstation-be | 8000 | Backend service |
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
│   │   │   ├── jwt_utils.py      # JWT for BE token
│   │   │   ├── curr_time.py      # Current time helper
│   │   │   ├── detect_language.py
│   │   │   └── tstation_be_api_client/  # Generated OpenAPI client
│   │   ├── config/               # Configuration (env.py, tracing.py)
│   │   ├── schemas/              # Pydantic models
│   │   └── services/
│   │       └── tstation/
│   │           ├── chat_v3/     # Current agent/runtime entrypoint
│   │           │   ├── service.py             # V3 orchestration entrypoint
│   │           │   ├── router/                # LLM-first route/guard/domain/tool decision
│   │           │   ├── executor.py            # Tool loop over shared tools
│   │           │   ├── templates.py           # Tool output → FE template payloads
│   │           │   ├── composer.py            # assistantResponse + quick replies
│   │           │   └── qc.py                  # V3 verification
│   │           ├── agents/      # Shared tools/schema + legacy V2 agents
│   │           │   ├── b_discovery_agent/     # Product search/recommendation tools
│   │           │   ├── c_transaction_agent/   # Price, store, booking, order tools
│   │           │   ├── e_support_agent/       # FAQ, warranty, escalation tools
│   │           │   └── templates/             # Pydantic schemas for FE templates
│   │           ├── common/
│   │           │   ├── pii_guardrail.py       # PII check before processing
│   │           │   └── tstation_be_client.py  # BE token injection
│   │           ├── chat_history_service.py    # Redis history/slots/tool_context
│   │           ├── chat.py                    # API branch + legacy V2 compatibility
│   │           └── template_mapper.py         # Legacy V2 tool → UI template mapping
│   ├── tstation-be-openapi.json               # OpenAPI spec for BE
│   ├── tstation-ingestion/       # FAQ ingestion into Qdrant
│   └── tstation-ui-demo/         # Streamlit demo UI
├── docker/
│   └── config/llm/conf-gateway.yaml  # LiteLLM gateway model config
├── docs/                        # Documentation
└── pyproject.toml
```

## Chat V3 Runtime

The current runtime starts in `services/tstation/chat_v3/service.py`, with routing in `chat_v3/router/`, tool
execution in `chat_v3/executor.py`, and response/template/QC handling in `chat_v3/composer.py`,
`chat_v3/templates.py`, and `chat_v3/qc.py`.

V3 reuses selected tools and schemas from `services/tstation/agents/`, but that folder is not the root runtime.

### Shared Legacy Agent Surfaces

| Folder | Current use |
|--------|-------------|
| b_discovery_agent | Product search, recommendations, compatibility, price tools reused by V3 |
| c_transaction_agent | Price, store, booking, orders, cart, order tracking tools reused by V3 |
| e_support_agent | FAQ, RAG, warranty, escalation tools reused by V3 |
| templates | FE template Pydantic schemas shared by V2/V3 |
| a_/f_/g_ agents | Legacy V2 compatibility or shared implementations |

### Agent Flow Events

```python
{"type": "status",      "status": "생각 중..."}
{"type": "status",      "status": "tool_start", "tool": "search_product_tool", "display_name": "상품 검색 중..."}
{"type": "agent_flow",  "agent": "[PRICE AF]", "status": "success"}
{"type": "token",       "content": "안녕하세요..."}
{"type": "tool",        "tool": "get_final_price_tool", "input": {...}, "output": "..."}
{"type": "message",     "content": "...", "agent": "[TRANSACTION AGENT]"}
{"type": "data",        "template": "product", "data": {...}}
{"type": "sub-agent",   "agent": "[DONE]", "status": "success"}
{"type": "DONE"}
```

### Chat V3 Flow

1. API layer calls `TStationChatServiceV2.chat()` as the branch gate.
2. With `AI_CHAT_V3_PURE_LLM_ENABLED=true`, it delegates to `TStationChatServiceV3.chat()`.
3. `chat_v3/router` produces the guard/domain/intent/slot/tool decision.
4. `chat_v3/executor.py` runs the required shared tools.
5. `chat_v3/templates.py`, `composer.py`, and `qc.py` build the final SSE-compatible response.
6. `chat_v3/sse.py` emits FE-compatible events.

### State Management (Redis)

| Key type | Content | Managed by |
|----------|---------|-----------|
| Chat history | Full conversation messages | `chat_history_service.py` |
| Slots | goods_no, tire_size, shop_id, quantity, intent | `chat_v3` routing/context plus shared Redis state |
| Tool context | Last tool outputs (filter_for_context) | `g_qc_agent/source_filter.py` |
| Template data | UI card data attached to assistant messages | `chat_history_service.py` |

### UI Templates (FE Contract)

V3 outputs structured `data` events:

| Template | Agent | Trigger |
|----------|-------|---------|
| `product` | `chat_v3/templates.py` | Product search/recommendations |
| `location` | `chat_v3/templates.py` | Store list |
| `datepick` | `chat_v3/templates.py` | Booking schedule |
| `preorder` | `chat_v3/templates.py` | Pre-order preview |
| `orderComplete` | `chat_v3/templates.py` | Order confirmed |
| `voucher` | `chat_v3/templates.py` | Coupon list |
| `listCar` | `chat_v3/templates.py` | Car model selection |
| `youtube` | `chat_v3/templates.py` | Video search results |
| `quickReply` | any | Suggested replies |

## LLM Configuration

| Env var | Default | Usage |
|---------|---------|-------|
| AI_MODEL | gpt-5.4 | UI Template Agent, router |
| AI_MODEL_REASONING | gpt-5.4-reasoning | All main sub-agents |
| AI_QC_MODEL | gpt-4o-mini | QC Agent (disabled) |
| AI_DEFAULT_PROVIDER | openai | LiteLLM provider prefix |
| AI_GATEWAY_BASE_URL | http://ai-gateway:8000/v1 | Internal LiteLLM proxy |

## Key Dependencies

### tstation-ai
- `fastapi`, `uvicorn` — API server
- `langchain`, `langchain-litellm` — Agent framework + LLM
- `qdrant-client` — Vector store for FAQ RAG
- `celery`, `redis` — Queue + conversation history
- `langfuse` — Tracing + observability
- `pydantic-settings` — Config management

### tstation-ui-demo
- `streamlit` — Demo UI

## API Endpoints

### T-Station AI
- `POST /tstation/chat` — Main chat endpoint (SSE streaming)
- `GET /tstation/chat/example_questions/{language}` — Example questions

### Monitoring
- `GET /health` — Health check
- `GET /metrics` — Prometheus metrics

## Development

- Python 3.12
- Package manager: `uv`
- Linting: `ruff`
- Task runner: `just`
