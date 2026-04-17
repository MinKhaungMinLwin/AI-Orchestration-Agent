# T-Station AI Full Architecture (Mermaid)

This document compiles two important architecture diagrams into one place:

1. Overall System Design (service, data, integrations).
2. AI orchestration + end-to-end tire purchase flow.

## 1) Architecture Diagram (System Design)

```mermaid
flowchart TB
    subgraph Client
      U[User]
      UI[tstation-ui-demo Streamlit]
      U --> UI
      UI --> U
    end

    subgraph AI["tstation-ai FastAPI"]
      EP[Chat Endpoint<br/>POST /tstation/messages/chat]
      SESS[Session APIs<br/>/tstation/messages/sessions<br/>/history/{session_id}]
      CS[TStationChatServiceV2<br/>classify_multi_intent → stream → QC]
      HS[ChatHistoryService]
      EP --> CS
      SESS --> HS
      CS --> HS
    end

    subgraph Agents["Multi-Agent Layer (orchestrated by Coordinator)"]
      CO[StreamingMultiAgentCoordinator<br/>decide_next_action]
      L[a_leading_agent<br/>no tools]
      D[b_discovery_agent]
      T[c_transaction_agent]
      S[e_support_agent]
      UT[f_ui_template_agent]
      CO -->|domain=LEADING| L
      CO -->|domain=DISCOVERY| D
      CO -->|domain=TRANSACTION| T
      CO -->|domain=SUPPORT| S
      CO -->|after agents, if tool data| UT
    end

    QC[g_qc_agent<br/>fact-check draft vs tools]

    subgraph External
      LLM[LiteLLM / AI Gateway]
      REDIS[(Redis: history/slots/tool_ctx)]
      QDRANT[(Qdrant: RAG)]
      BE[tstation-be APIs via OpenAPI client]
      ORACLE[(Oracle DB)]
      LANG[Langfuse<br/>global config/tracing]
    end

    subgraph Ingestion["tstation-ingestion"]
      ING[Ingestion Service]
    end

    UI -->|POST /api/tstation/messages/chat SSE| EP
    UI -->|GET/DELETE session APIs| SESS
    EP -->|SSE: token/tool/data/message + DONE| UI

    CS -->|1. classify + inject context| CO
    CS -->|3. fact-check after CO done| QC

    L --> LLM
    D --> LLM
    T --> LLM
    S --> LLM
    UT --> LLM
    QC --> LLM

    HS --> REDIS
    S --> QDRANT
    D --> BE
    T --> BE
    S --> BE
    BE --> ORACLE
    AI -.->|global init| LANG

    ING --> QDRANT
```

## 2) Sequence Diagram — Full Agent Flow

```mermaid
sequenceDiagram
    autonumber
    participant U as User/UI
    participant API as POST /tstation/messages/chat
    participant R as Redis
    participant V2 as TStationChatServiceV2
    participant CO as StreamingMultiAgentCoordinator
    participant L as a_leading_agent
    participant D as b_discovery_agent
    participant T as c_transaction_agent
    participant S as e_support_agent
    participant UT as f_ui_template_agent
    participant B as tstation-be APIs
    participant QDRANT as Qdrant RAG
    participant QC as g_qc_agent

    U->>API: Chat request (message, session, access_token, stream)
    API->>R: save user message to Redis history
    API->>V2: TStationChatServiceV2.chat(request)

    Note over V2: set_tstation_be_token → PII guardrail check
    V2->>R: load template_data + slots + tool_context
    V2->>R: merge/save slots

    V2->>CO: classify_multi_intent(messages)
    CO-->>V2: ordered domain list e.g. [DISCOVERY, TRANSACTION]
    Note over V2: inject CONVERSATION CONTEXT into last user message

    V2->>CO: stream(messages, domains, slot_context, tool_context)

    alt domain = LEADING (greeting / unclear intent / small talk)
        CO->>L: stream(enriched_messages)
        Note over L: No tools — pure LLM conversational response
        L-->>CO: token stream + message event
    end

    alt domain = DISCOVERY (product search, recommendation, compatibility)
        CO->>D: stream(enriched_messages)
        D->>B: search_product / check_compatibility / get_recommendations / get_description / get_events / get_deals / compare_discount / search_youtube
        B-->>D: product data (goods_no, tire_size, etc.)
        D-->>CO: tool events + token stream + message event
        CO->>R: save slot(goods_no, tire_size, shop_id) from tool output
    end

    Note over CO: decide_next_action() — LLM decides STOP or CONTINUE after first agent
    alt CONTINUE → TRANSACTION
        CO->>T: stream(enriched_messages + handover context + accumulated_tool_data)
        T->>B: get_final_price / get_logistics_inventory / get_store_inventory / get_nearby_stores / quick_order / save_to_cart
        B-->>T: commerce data + order/cart result
        T-->>CO: tool events + token stream + message event
        CO->>R: update tool context
    end

    alt domain = SUPPORT (FAQ / warranty / escalation)
        CO->>S: stream(enriched_messages)
        S->>B: get_faq / escalate
        S->>QDRANT: search_faq_rag_tool (RAG)
        B-->>S: support data
        S-->>CO: tool events + token stream + message event
        Note over CO: Support domain → always STOP, skip decide_next_action
    end

    alt tool data exists AND (non-support tools OR qna transfer)
        Note over CO,UT: V2 emits waiting event before UT starts
        CO->>UT: stream_template(ui_messages + accumulated_tool_data)
        UT-->>CO: data events (UI templates for frontend)
    end

    CO-->>V2: all events (tokens intercepted by V2; tool/data/sub-agent passed through)

    Note over V2: QC Layer — called by V2, NOT by Coordinator
    alt tool data exists AND draft has factual claims
        V2->>QC: stream_qc(user_query, draft_response, source_data)
        alt QC PASS
            QC-->>V2: "PASS" → keep draft as final
        else QC CORRECT
            QC-->>V2: corrected token stream → override draft
        end
    else no factual claims (greeting, FAQ only)
        Note over V2: skip QC — pass draft directly
    end

    V2->>R: save tool_context_items for next turn
    V2-->>U: SSE: agent_flow / sub-agent / tool / token / data / message events
    V2-->>U: {"type": "DONE"}
    V2-->>U: data: [DONE]
```