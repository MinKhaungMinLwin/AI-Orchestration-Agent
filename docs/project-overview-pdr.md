# T-Station AI Project Overview

## Project Summary

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea using a multi-agent AI architecture. The system provides product recommendations, compatibility checks, store information, and support.

## Business Context

- **Client**: Hankook Tire Korea
- **Purpose**: AI-powered customer support for tire sales
- **Languages**: Korean, English, Vietnamese, Chinese, Japanese

## Service Ports

| Service | Port |
|---------|------|
| tstation-ai | 9000 |
| tstation-be | 8000 |
| tstation-ui-demo | 7777 |

## Technical Stack

- **API Framework**: FastAPI + Uvicorn
- **AI/LLM**: LangChain + LiteLLM with Bedrock Claude Haiku 4.5
- **Task Queue**: Celery + Redis
- **Observability**: Langfuse

## PDR

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-001 | Multi-agent chat system | Critical |
| FR-002 | Domain classification (LEADING, DISCOVERY, TRANSACTION, SUPPORT) | Critical |
| FR-003 | Product discovery with recommendations | High |
| FR-004 | Store/shopping agent | High |
| FR-005 | Support agent (policies, FAQ) | High |
| FR-006 | Multi-language support | High |

### Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| First response time | <3s |
| System uptime | 99.5% |
| FAQ resolution rate | >85% |

---

## Architecture

### Agents

| Agent | Purpose |
|-------|---------|
| a_leading_agent | Orchestrator, domain routing |
| b_discovery_agent | Product recommendations, compatibility |
| c_transaction_agent | Orders, purchase intent, price, stock, store |
| e_support_agent | Policies, warranty, FAQ |

### Domain Routing

| Domain | Agent |
|--------|-------|
| LEADING | Leading |
| DISCOVERY | Discovery |
| TRANSACTION | Transaction |
| SUPPORT | Support |

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Classification Accuracy | >90% |
| First Response Time | <3s |
| System Uptime | 99.5% |
| FAQ Resolution Rate | >85% |

---

## Risks & Mitigation

| Risk | Mitigation |
|------|------------|
| LLM response quality | Prompt engineering |
| Classification errors | Fallback to leading agent |
| Oracle DB performance | Connection pooling, caching |
