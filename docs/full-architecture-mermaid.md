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
      CS[TStationChatServiceV2]
      CO[StreamingMultiAgentCoordinator]
      QC[QC Agent]
      UT[UI Template Agent]
      HS[ChatHistoryService]
      EP --> CS --> CO
      SESS --> HS
      CO --> QC
      CO --> UT
      CS --> HS
    end

    subgraph Agents["Multi-Agent Layer"]
      L[a_leading_agent]
      D[b_discovery_agent]
      T[c_transaction_agent]
      S[e_support_agent]
    end

    subgraph External
      LLM[LiteLLM / AI Gateway]
      REDIS[(Redis: history/slots/tool_ctx)]
      QDRANT[(Qdrant: RAG)]
      BE[tstation-be APIs via OpenAPI client]
      ORACLE[(Oracle DB)]
      LANG[Langfuse config/tracing]
    end

    UI -->|POST /api/tstation/messages/chat SSE| EP
    UI -->|GET/DELETE session APIs| SESS
    EP -->|SSE: token/tool/data/message + DONE| UI
    CO --> L
    CO --> D
    CO --> T
    CO --> S

    L --> LLM
    D --> LLM
    T --> LLM
    S --> LLM

    HS --> REDIS
    D --> QDRANT
    D --> BE
    T --> BE
    S --> BE
    BE --> ORACLE
    CS --> LANG
```

## 2) Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant U as User/UI
    participant API as /tstation/messages/chat
    participant V2 as TStationChatServiceV2
    participant R as Redis
    participant C as Coordinator
    participant D as Discovery Agent
    participant T as Transaction Agent
    participant S as Support Agent
    participant UT as UI Template Agent
    participant B as tstation-be APIs
    participant Q as QC Agent

    U->>API: Chat request (message, session, token, stream)
    API->>R: save user message/history
    API->>V2: chat(request)
    V2->>V2: set_tstation_be_token + PII guardrail
    V2->>R: load template_data + slots + tool_context
    V2->>R: merge/save slots
    V2->>C: classify_multi_intent + start stream

    alt Intent includes discovery (tire search, compatibility, recommendation)
        C->>D: stream(messages + context)
        D->>B: search_product / compatibility / recommendations / description
        B-->>D: product data + goods_no + tire_size
        D-->>C: tool events + draft response
        C->>R: save slot(goods_no,tire_size,shop_id) + tool context
    end

    C->>C: decide_next_action (STOP/CONTINUE)
    alt CONTINUE to transaction (price/inventory/store/purchase)
        C->>T: stream(handover context from discovery)
        T->>B: final_price / inventory / nearby_stores / quick_order or save_to_cart
        B-->>T: commerce data + order/cart result
        T-->>C: unified commerce response
        C->>R: update tool context
    end

    alt Support request (warranty/FAQ/escalation)
        C->>S: stream()
        S->>B: faq/escalate
        B-->>S: support data
        S-->>C: support response
    end

    alt has non-support tool data or qna transfer
        C->>UT: stream_template(ui messages)
        UT-->>C: data events for frontend templates
    end

    C->>Q: fact-check draft vs tool outputs
    alt QC PASS
        Q-->>C: PASS (keep draft)
    else QC CORRECT
        Q-->>C: corrected answer stream
    end

    C-->>U: SSE: agent_flow/sub-agent/tool/token/data/message
    C-->>U: final {"type":"DONE"} + [DONE]
```

## Validation Notes Based on Code

- The repo currently does not contain the actual running source code for `app/tstation-be`; the AI service calls the BE via a generated OpenAPI client.
- The actual chat endpoint is `/tstation/messages/chat` in `api/tstation/chat_message.py` (mounted by `api/router.py`).
- The UI demo currently has differences in the base URL between modules (`chat.py` uses `/api`, while `sessions.py` does not), so the diagram reflects the primary chat calling path.
- The sequence has been updated to include the `UI Template Agent` step and the finalize stream (`DONE` + `[DONE]`), consistent with `_stream_response_multi()`.
