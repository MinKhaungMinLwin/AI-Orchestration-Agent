# T-Station AI Full Architecture (Mermaid)

This document compiles two important architecture diagrams:

1. Overall System Design (services, data, integrations).
2. AI orchestration + end-to-end chat flow.

Current agent/runtime entrypoint: `app/tstation-ai/services/tstation/chat_v3/` (`/chat_v3`). Before changing
runtime behavior, read `docs/chat-v3/MIGRATE_V2_TO_V3_EN.md`.

## 1) Architecture Diagram (System Design)

```mermaid
flowchart TB
    subgraph Client
      U[User]
      UI[tstation-ui-demo Streamlit]
      U --> UI
      UI --> U
    end

    subgraph AI["tstation-ai FastAPI :9000"]
      EP[Chat Endpoint<br/>POST /tstation/chat]
      CS[TStationChatServiceV3<br/>chat_v3/service.py]
      HS[ChatHistoryService<br/>Redis: history / slots / tool_ctx]
      EP --> CS
      CS --> HS
    end

    subgraph V3["Chat V3 Runtime"]
      ROUTER[chat_v3/router<br/>guard / domain / intent / slots / tool plan]
      EXEC[chat_v3/executor.py<br/>tool loop]
      COMP[chat_v3/composer.py<br/>assistantResponse / quick replies]
      TPL[chat_v3/templates.py<br/>FE template payloads]
      QC[chat_v3/qc.py<br/>verification]
      TOOLS[agents/*/tools.py<br/>shared tool surface]
      ROUTER --> EXEC
      EXEC --> TOOLS
      EXEC --> TPL
      TPL --> COMP
      QC --> COMP
    end

    subgraph External
      GW[LiteLLM AI Gateway<br/>GPT-5.4-reasoning / GPT-5.4 / GPT-4o-mini]
      REDIS[(Redis<br/>history / slots / tool_ctx)]
      QDRANT[(Qdrant<br/>FAQ RAG)]
      BE[tstation-be APIs<br/>OpenAPI client]
      ORACLE[(Oracle DB)]
      LANG[Langfuse<br/>tracing]
    end

    subgraph Ingestion["tstation-ingestion"]
      ING[FAQ Ingestion → Qdrant]
    end

    UI -->|POST /api/tstation/chat SSE| EP
    EP -->|SSE: token/tool/data/message/DONE| UI

    CS --> ROUTER
    ROUTER --> GW
    COMP --> GW
    QC --> GW

    HS --> REDIS
    TOOLS --> QDRANT
    TOOLS --> BE
    BE --> ORACLE
    AI -.->|tracing| LANG
    ING --> QDRANT
```

## 2) Sequence Diagram — Full Agent Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as User/UI
    participant API as POST /tstation/chat
    participant R as Redis
    participant CS as TStationChatServiceV3
    participant RT as chat_v3/router
    participant EX as chat_v3/executor
    participant TL as agents/*/tools.py
    participant CP as chat_v3/templates/composer/qc
    participant B as tstation-be APIs
    participant QDRANT as Qdrant RAG

    U->>API: Chat request (message, session_id, access_token, stream=true)
    API->>R: save user message to history
    API->>CS: TStationChatServiceV2.chat(request) branch gate → V3

    Note over CS: set_tstation_be_token → PII guardrail check
    CS->>R: load history + template_data + slots + tool_context
    CS->>RT: route_request(messages + context)
    RT-->>CS: guard/domain/intent/slots/tool plan

    CS->>EX: run tool loop(route decision)
    EX->>TL: call selected shared tools
    TL->>B: product / price / store / order / FAQ APIs
    TL->>QDRANT: FAQ RAG search when needed
    B-->>TL: backend data
    QDRANT-->>TL: RAG results
    TL-->>EX: tool outputs
    EX-->>CS: tool events + results

    CS->>CP: build assistantResponse, templates, quick replies, QC
    CP-->>CS: message/data events

    CS->>R: save tool_context_items for next turn
    CS-->>U: SSE: agent_flow / sub-agent / tool / token / data / message events
    CS-->>U: {"type": "DONE"}
    CS-->>U: data: [DONE]
```

## 3) SSE Event Schema (FE Contract)

```
data: {"type": "agent_flow",  "agent": "[응답 생성 중]",   "status": "processing"}
data: {"type": "status",      "status": "생각 중..."}
data: {"type": "status",      "status": "tool_start", "tool": "search_product_tool", "display_name": "상품 검색 중..."}
data: {"type": "agent_flow",  "agent": "[PRICE AF]",        "status": "success"}
data: {"type": "token",       "content": "안녕하세요..."}
data: {"type": "tool",        "tool": "get_final_price_tool", "input": {...}, "output": "..."}
data: {"type": "message",     "content": "...", "agent": "[TRANSACTION AGENT]"}
data: {"type": "data",        "template": "product", "data": {"assistantResponse": "...", "meta": {...}, "items": [...]}}
data: {"type": "sub-agent",   "agent": "[DONE]",            "status": "success"}
data: {"type": "DONE"}
data: [DONE]
```
