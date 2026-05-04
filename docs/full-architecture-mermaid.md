# T-Station AI Full Architecture (Mermaid)

This document compiles two important architecture diagrams:

1. Overall System Design (services, data, integrations).
2. AI orchestration + end-to-end chat flow.

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
      CS[TStationChatService<br/>StreamingMultiAgentCoordinator]
      HS[ChatHistoryService<br/>Redis: history / slots / tool_ctx]
      EP --> CS
      CS --> HS
    end

    subgraph Agents["Multi-Agent Layer"]
      CO[StreamingMultiAgentCoordinator<br/>classify_multi_intent → route → decide_next_action]
      L[a_leading_agent<br/>no tools — pure LLM]
      D[b_discovery_agent<br/>product search / compat / price]
      T[c_transaction_agent<br/>store / booking / orders]
      S[e_support_agent<br/>FAQ RAG / escalation]
      UT[f_ui_template_agent<br/>UI card rendering]
      QC["g_qc_agent<br/>fact-check ⚠️ DISABLED"]
      CO -->|LEADING| L
      CO -->|DISCOVERY| D
      CO -->|TRANSACTION| T
      CO -->|SUPPORT| S
      CO -->|tool data & no direct data event| UT
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

    CS --> CO
    L --> GW
    D --> GW
    T --> GW
    S --> GW
    UT --> GW
    QC -.->|disabled| GW

    HS --> REDIS
    S --> QDRANT
    D --> BE
    T --> BE
    S --> BE
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
    participant CS as TStationChatService
    participant CO as StreamingMultiAgentCoordinator
    participant L as a_leading_agent
    participant D as b_discovery_agent
    participant T as c_transaction_agent
    participant S as e_support_agent
    participant UT as f_ui_template_agent
    participant B as tstation-be APIs
    participant QDRANT as Qdrant RAG

    U->>API: Chat request (message, session_id, access_token, stream=true)
    API->>R: save user message to history
    API->>CS: TStationChatService.chat(request)

    Note over CS: set_tstation_be_token → PII guardrail check
    CS->>R: load history + template_data + slots + tool_context
    CS->>R: merge/save slots (goods_no, tire_size, shop_id, qty)

    CS->>CO: classify_multi_intent(messages)
    CO-->>CS: domain list e.g. [DISCOVERY] + routing context
    Note over CS: inject CONVERSATION CONTEXT into last user message<br/>(user_behavior, next_action, flow)

    CS->>CO: stream(messages, domains, slot_context, tool_context)

    alt domain = LEADING
        CO->>L: stream(enriched_messages)
        Note over L: No tools — pure LLM response
        L-->>CO: token + message events
    end

    alt domain = DISCOVERY
        CO->>D: stream(enriched_messages)
        D->>B: search_product / check_compatibility / get_recommendations<br/>get_final_price / get_events / get_deals / compare_discount / search_youtube
        B-->>D: product + price data
        D-->>CO: tool events + token + message events
    end

    Note over CO: decide_next_action() — STOP or CONTINUE

    alt CONTINUE → TRANSACTION
        CO->>T: stream(enriched_messages + context + accumulated_tool_data)
        T->>B: get_final_price / get_store_list / get_store_schedule<br/>quick_order / save_to_cart / get_order_status
        B-->>T: commerce data + order results
        T-->>CO: tool events + token + message events
    end

    alt domain = SUPPORT
        CO->>S: stream(enriched_messages)
        S->>B: get_faq / escalate
        S->>QDRANT: search_faq_rag_tool
        B-->>S: support data
        S-->>CO: tool events + token + message events
        Note over CO: Support → always STOP
    end

    alt agent called tools AND no direct data event emitted
        CO->>UT: stream(messages + accumulated_tool_data)
        UT-->>CO: data events (UI templates for FE)
    end

    CO-->>CS: all events streamed

    Note over CS: QC DISABLED — skip fact-check
    CS->>CS: _sanitize_response() — remove backend jargon

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
