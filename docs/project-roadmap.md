# T-Station AI Project Roadmap

## Phase Overview

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Foundation | Complete | Core infrastructure and backend |
| Phase 2: AI Agents | Complete | Multi-agent system |
| Phase 3: Shopping/Support | In Progress | Shopping and Support agents |
| Phase 4: Production | Pending | Production hardening |

---

## Phase 1: Foundation (Complete)

- FastAPI setup for tstation-ai
- Backend service (tstation-be) with Oracle integration
- API routers for shop, price, inventory, recommendation
- Docker containerization

---

## Phase 2: AI Agents (Complete)

- Leading Agent (domain classifier)
- Discovery Agent for product recommendations
- Transaction Agent (partial)
- Multi-language support
- Streaming response support

---

## Phase 3: Shopping/Support (In Progress)

### Current Tasks

| Task | Status |
|------|--------|
| Shopping Agent implementation | In Progress |
| Support Agent implementation | In Progress |
| Transaction Agent completion | Pending |

### Agents

| Agent | Status |
|-------|--------|
| a_leading_agent | Complete |
| b_discovery_agent | Complete |
| c_transaction_agent | Partial |
| d_shopping_agent | Partial |
| e_support_agent | Partial |

---

## Phase 4: Production Hardening (Pending)

- Performance optimization
- Comprehensive testing
- Security audit
- Monitoring and alerting

---

## Technical Debt

| Item | Priority |
|------|----------|
| Agent completion | High |
| Unit tests | High |
| Integration tests | Medium |

---

## Dependencies

- Oracle database
- AWS Bedrock
- Qdrant vector store
- Langfuse
