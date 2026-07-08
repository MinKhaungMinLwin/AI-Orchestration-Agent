# T-Station AI Code Standards

## General Guidelines

### Language & Version
- **Python**: 3.12
- **Package Manager**: uv

### File Naming
- Use **kebab-case** for file names
- Descriptive names that indicate purpose

### Code Organization
- Keep files under 300 lines where possible
- Split large files into focused modules
- Use composition over inheritance

---

## Code Style

### Line Length
- Maximum 120 characters

### Imports
- Use ruff for import sorting
- Group: standard library, third-party, local
- Use absolute imports within package

### Type Hints
- Use type hints for parameters and return types

### Error Handling
- Use try-catch for error handling
- Log exceptions with appropriate level
- Return meaningful error messages

---

## Project Structure

```
app/
├── tstation-ai/              # Main AI service
│   ├── api/                  # API endpoints
│   ├── common/               # Shared utilities
│   ├── config/               # Configuration
│   ├── schemas/              # Pydantic models
│   └── services/
│       └── tstation/
│           ├── chat_v3/     # Current agent/runtime entrypoint
│           │   ├── service.py             # V3 orchestration entrypoint
│           │   ├── router/                # LLM-first routing/guard/tool decision
│           │   ├── executor.py            # Tool loop
│           │   ├── templates.py           # Tool output → FE templates
│           │   ├── composer.py            # assistantResponse + quick replies
│           │   └── qc.py                  # Verification
│           ├── agents/      # Shared tools/schema + legacy V2 agents
│           │   ├── b_discovery_agent/
│           │   ├── c_transaction_agent/
│           │   ├── e_support_agent/
│           │   └── templates/             # FE template Pydantic schemas
│           ├── common/
│           ├── chat_history_service.py
│           ├── chat.py                    # API branch + legacy V2 compatibility
│           └── template_mapper.py         # Legacy V2 template mapper
├── tstation-be-openapi.json  # OpenAPI spec (generated BE client)
└── tstation-ui-demo/         # Streamlit demo UI
```

---

## Chat V3 Runtime

Current runtime work starts in `services/tstation/chat_v3/`. Read `docs/chat-v3/MIGRATE_V2_TO_V3_EN.md` before
changing routing, tool execution, templates, QC, or SSE behavior.

### Shared Legacy Agent Directory

The `agents/` directory is not the current root runtime. It provides shared tools/schema and legacy V2 compatibility.
Use prefix ordering (a_, b_, c_, ...) only when working in that legacy/shared surface:

```
agents/
├── base_agent.py            # Legacy BaseAgent + shared display names
├── a_leading_agent/         # Legacy V2 leading agent
├── b_discovery_agent/       # Shared product search/recommendation tools
├── c_transaction_agent/     # Shared price/store/booking/order tools
├── e_support_agent/         # Shared FAQ/warranty/escalation tools
├── f_ui_template_agent/     # Legacy V2 UI card rendering
├── g_qc_agent/              # Legacy/shared QC implementation
└── templates/               # FE template Pydantic schemas shared by V2/V3
```

### Legacy BaseAgent Implementation

Legacy V2 agents inherit from `BaseAgent`. New V3 routing/composition behavior belongs in `chat_v3/` unless the
shared tool/schema contract itself is changing:

```python
from services.tstation.agents.base_agent import BaseAgent

class MyAgent(BaseAgent):
    TOOL_TO_AF_MAP = {
        "tool_name_1": "Agent Function Name",
        "tool_name_2": "Another Function",
    }

    def __init__(self, model):
        super().__init__(
            model=model,
            tools=[tool1, tool2],
            system_prompt=MY_PROMPT,
            name="[MY AGENT]",
        )
```

### Agent System Prompts

- System prompts define all flows the agent handles
- Use numbered flows: `Flow 1`, `Flow 2`, etc.
- Each flow has numbered steps
- Keep rules explicit to avoid LLM hallucination
- Use `⚠️` markers for critical/override rules

### Tools

Each agent has a `tools.py` file. Tools use LangChain `@tool` decorator:

```python
from langchain_core.tools import tool

@tool
def my_tool(param: str) -> str:
    """Clear docstring describing what the tool does."""
    ...
```

- Tool return format: JSON string or dict
- Include `status: "success" | "error"` in returns
- Parallel fetch with `ThreadPoolExecutor` for multi-item lookups

---

## UI Template System

Agents emit structured `data` events for FE rendering. Templates defined in `templates/schemas.py`:

```python
class ProductItem(BaseModel):
    goods_no: str
    name: str
    price: Optional[int] = Field(None, ge=0)
    ...

class ProductDataEvent(BaseModel):
    type: Literal["data"] = "data"
    template: Literal["product"] = "product"
    data: ProductTemplate
```

Rules:
- `assistantResponse` field is the text shown in chat
- Agent must populate ALL required fields
- `price: Optional[int]` — omit if price unavailable (never use 0)

---

## Streaming SSE Contract

Events yielded by agents (base_agent.py) and coordinator (chat.py):

```
data: {"type": "status",     "status": "생각 중..."}
data: {"type": "agent_flow", "agent": "[DISCOVERY AGENT]", "status": "success"}
data: {"type": "token",      "content": "..."}
data: {"type": "tool",       "tool": "search_product_tool", "input": {...}, "output": "..."}
data: {"type": "message",    "content": "...", "agent": "[DISCOVERY AGENT]"}
data: {"type": "data",       "template": "product", "data": {...}}
data: {"type": "sub-agent",  "agent": "[DONE]", "status": "success"}
data: {"type": "DONE"}
data: [DONE]
```

- `token` events stream in real-time (TTFT)
- `message` events are held until after QC, then yielded last (history sync)
- `data` events pass through immediately (UI card rendering)

---

## LLM Models

| Use case | Model | Notes |
|----------|-------|-------|
| Main sub-agents | `gpt-5.4-reasoning` | Deep reasoning for complex flows |
| UI template rendering | `gpt-5.4` | Fast template mapping |
| Router classification | `gpt-5.4` | Classify domain |
| QC Agent | `gpt-4o-mini` | Lightweight fact-check |

Configure via env vars: `AI_MODEL`, `AI_MODEL_REASONING`, `AI_QC_MODEL`

---

## Environment Variables

Key variables in `.env`:

```env
AI_DEFAULT_PROVIDER=openai
AI_GATEWAY_BASE_URL=http://ai-gateway:8000/v1
AI_GATEWAY_API_KEY=...
AI_MODEL=gpt-5.4
AI_MODEL_REASONING=gpt-5.4-reasoning
AI_QC_MODEL=gpt-4o-mini
```

---

## Development

- Python 3.12
- Package manager: `uv`
- Linting: `ruff`
- Task runner: `just`
- Tracing: Langfuse (all LLM calls traced with session/user/trace IDs)
