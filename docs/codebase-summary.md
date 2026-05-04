# T-Station AI Codebase Summary

## Overview

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea. Multi-agent architecture built with FastAPI + LangGraph, streaming SSE responses to frontend.

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
│   │           ├── agents/      # AI Agents
│   │           │   ├── base_agent.py          # Base class (streaming + events)
│   │           │   ├── router.py              # LLM instances + agent singletons
│   │           │   ├── a_leading_agent/       # Greeting / unclear intent
│   │           │   ├── b_discovery_agent/     # Product search, recommendations
│   │           │   ├── c_transaction_agent/   # Price, store, booking, orders
│   │           │   ├── e_support_agent/       # FAQ, warranty, escalation (RAG)
│   │           │   ├── f_ui_template_agent/   # UI card rendering
│   │           │   ├── g_qc_agent/            # QC fact-check (DISABLED)
│   │           │   └── templates/             # Pydantic schemas for FE templates
│   │           ├── common/
│   │           │   ├── pii_guardrail.py       # PII check before processing
│   │           │   └── tstation_be_client.py  # BE token injection
│   │           ├── chat_history_service.py    # Redis history/slots/tool_context
│   │           ├── chat.py                    # Main coordinator + stream pipeline
│   │           └── template_mapper.py         # tool → UI template mapping
│   ├── tstation-be-openapi.json               # OpenAPI spec for BE
│   ├── tstation-ingestion/       # FAQ ingestion into Qdrant
│   └── tstation-ui-demo/         # Streamlit demo UI
├── docker/
│   └── config/llm/conf-gateway.yaml  # LiteLLM gateway model config
├── docs/                        # Documentation
└── pyproject.toml
```

## AI Agents

### BaseAgent (base_agent.py)

All agents inherit from `BaseAgent`:

```python
class BaseAgent(ABC):
    TOOL_TO_AF_MAP: dict[str, str] = {}      # Tool → AF display name
    TOOL_TO_TEMPLATE_MAP: dict[str, str] = {} # Tool → UI template type
    RESPONSE_FORMAT: type[BaseModel] | None = None
    OUTPUT_TEMPLATE: Any = None               # Structured output template

    def stream(self, messages: list[dict], config=None):
        # Yields: status, agent_flow, token, message, tool_start, tool, data events
```

### Agent Classes

| Agent | Purpose | Model |
|-------|---------|-------|
| a_leading_agent | Greeting, unclear intent, small talk | GPT-5.4-reasoning |
| b_discovery_agent | Product search, recommendations, compatibility, price | GPT-5.4-reasoning |
| c_transaction_agent | Price, store, booking, orders, cart, order tracking | GPT-5.4-reasoning |
| e_support_agent | FAQ (RAG), warranty, escalation | GPT-5.4-reasoning |
| f_ui_template_agent | Renders UI cards (product, location, datepick, preorder) | GPT-5.4 |
| g_qc_agent | Fact-check draft vs tool data — **DISABLED** | GPT-4o-mini |

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

### Multi-Agent Coordinator (chat.py)

`StreamingMultiAgentCoordinator` orchestrates all agents:

1. `classify_multi_intent()` → classify user message into domain(s)
2. Inject `CONVERSATION CONTEXT` (user_behavior, next_action, flow) into last user message
3. Route to agent(s) sequentially
4. `decide_next_action()` after each agent: STOP or CONTINUE
5. (Optional) `f_ui_template_agent` for UI card rendering
6. Local `_sanitize_response()` — remove backend jargon
7. QC Agent: **DISABLED** (controlled by `# QC AGENT DISABLED` in chat.py)
8. Yield final SSE stream to FE

### State Management (Redis)

| Key type | Content | Managed by |
|----------|---------|-----------|
| Chat history | Full conversation messages | `chat_history_service.py` |
| Slots | goods_no, tire_size, shop_id, quantity, intent | `chat.py` slot extractor |
| Tool context | Last tool outputs (filter_for_context) | `g_qc_agent/source_filter.py` |
| Template data | UI card data attached to assistant messages | `chat_history_service.py` |

### UI Templates (FE Contract)

Agents output structured `data` events:

| Template | Agent | Trigger |
|----------|-------|---------|
| `product` | b_discovery | Product search/recommendations |
| `location` | c_transaction | Store list |
| `datepick` | c_transaction | Booking schedule |
| `preorder` | c_transaction | Pre-order preview |
| `orderComplete` | c_transaction | Order confirmed |
| `voucher` | c_transaction | Coupon list |
| `listCar` | b_discovery | Car model selection |
| `youtube` | b_discovery | Video search results |
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
