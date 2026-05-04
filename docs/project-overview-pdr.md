# T-Station AI Project Overview

## Project Summary

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea using a multi-agent AI architecture. Built with FastAPI + LangGraph, the system provides tire product recommendations, compatibility checks, store search, reservation, ordering, and customer support via a streaming SSE chat interface.

## Business Context

- **Client**: Hankook Tire Korea
- **Purpose**: AI-powered customer support for tire sales (T-Station brand)
- **Primary Language**: Korean
- **Other Languages**: English, Vietnamese, Chinese, Japanese

## Service Ports

| Service | Port |
|---------|------|
| tstation-ai | 9000 |
| tstation-be | 8000 |
| tstation-ui-demo | 7777 |

## Technical Stack

- **API Framework**: FastAPI + Uvicorn
- **Agent Framework**: LangGraph (via LangChain)
- **LLM**: OpenAI GPT-5.4-reasoning (agents) / GPT-5.4 (router, UI template) / GPT-4o-mini (QC, disabled)
- **LLM Gateway**: LiteLLM (internal proxy, docker service)
- **Conversation State**: Redis (history, slots, tool context)
- **RAG**: Qdrant vector store (FAQ docs)
- **Observability**: Langfuse (tracing all LLM calls)
- **Task Queue**: Celery + Redis (async jobs)

## PDR

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-001 | Multi-agent chat system with domain routing | Critical |
| FR-002 | Domain classification (LEADING, DISCOVERY, TRANSACTION, SUPPORT) | Critical |
| FR-003 | Product discovery — search, recommendations, compatibility check | High |
| FR-004 | Transaction flows — price, store, booking, cart, quick order | High |
| FR-005 | Support agent — FAQ (RAG), warranty, human escalation | High |
| FR-006 | UI template system — product cards, store list, datepick, preorder | High |
| FR-007 | Streaming SSE responses (token-level) | High |
| FR-008 | Multi-turn conversation with slot/context persistence | High |

### Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| First token time | <2s |
| System uptime | 99.5% |
| FAQ resolution rate | >85% |
| Classification accuracy | >90% |

---

## Architecture

### Agents

| Agent | Purpose | Tools |
|-------|---------|-------|
| a_leading_agent | Greeting, unclear intent, small talk | None |
| b_discovery_agent | Product search, recommendations, compatibility, YouTube | search_product, check_compatibility, get_recommendations, get_final_price, compare_discount, get_events, get_deals, search_youtube |
| c_transaction_agent | Price, store, booking schedule, orders, cart | get_final_price, get_store_list, get_store_schedule, quick_order, save_to_cart, get_order_status, get_orders_of_user |
| e_support_agent | FAQ (RAG), warranty, human escalation | get_faq, search_faq_rag, escalate |
| f_ui_template_agent | Render UI cards from accumulated tool data | list_product, list_location, available_dates, preorder, order_complete, voucher, listCar, youtube |
| g_qc_agent | Fact-check draft vs tool data — **currently DISABLED** | None |

### Domain Routing

| Domain | Agent | When |
|--------|-------|------|
| LEADING | a_leading_agent | Greeting, unclear intent |
| DISCOVERY | b_discovery_agent | Product search, recommendation, compatibility |
| TRANSACTION | c_transaction_agent | Price, store, booking, purchase, order tracking |
| SUPPORT | e_support_agent | Warranty, returns, FAQ, escalation |

### UI Templates (FE)

| Template | Trigger |
|----------|---------|
| `product` | Product search / recommendations |
| `location` | Store list |
| `datepick` | Booking schedule |
| `preorder` | Pre-order preview |
| `orderComplete` | Order confirmed |
| `voucher` | Coupon list |
| `listCar` | Car model selection |
| `youtube` | Video search results |
| `quickReply` | Suggested quick replies |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Classification Accuracy | >90% |
| First Token Time | <2s |
| System Uptime | 99.5% |
| FAQ Resolution Rate | >85% |

---

## Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| LLM wrong flow | Explicit numbered flows in system prompt, ⚠️ override rules |
| Classification errors | Fallback to LEADING agent |
| Empty tool results | Agent must return helpful Korean message |
| Price showing as 0 | Discovery agent calls get_final_price_tool for all products |
| Slow latency | Parallel tool fetches (ThreadPoolExecutor), QC disabled |
