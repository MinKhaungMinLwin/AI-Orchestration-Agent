# T-Station AI Project Roadmap

## Overview

This document outlines the project phases, milestones, and progress for T-Station AI development.

---

## Phase Overview

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1: Foundation | Complete | Core infrastructure and backend |
| Phase 2: AI Agents | Complete | Multi-agent system implementation |
| Phase 3: RAG/FAQ | Complete | FAQ retrieval system |
| Phase 4: Store Integration | In Progress | Store agent development |
| Phase 5: Production | Pending | Production hardening |

---

## Phase 1: Foundation (Complete)

### Milestones

- [x] FastAPI setup for tstation-ai
- [x] Backend service (tstation-be) with Oracle integration
- [x] API routers for shop, price, inventory, recommendation
- [x] Basic monitoring and health checks
- [x] Docker containerization
- [x] Development environment setup

### Key Deliverables

- Main AI service running on FastAPI
- Backend REST API with 10+ endpoints
- Docker Compose for local development

---

## Phase 2: AI Agents (Complete)

### Milestones

- [x] Leading Agent implementation (domain classifier)
- [x] Discovery Agent for product recommendations
- [x] Compatibility checking tools
- [x] Multi-language support (EN, KO, VI, ZH, JA)
- [x] Streaming response support

### Key Deliverables

- Multi-agent architecture with domain routing
- Product recommendation capabilities
- Language detection and response

---

## Phase 3: RAG/FAQ (Complete)

### Milestones

- [x] FAQ Agent implementation
- [x] Qdrant vector store integration
- [x] OpenAI integration for response generation
- [x] Scripts for loading FAQs to vector store
- [x] RAG flow implementation

### Key Deliverables

- RAG-based FAQ retrieval
- Policy question answering
- Vector store management scripts

---

## Phase 4: Store Integration (In Progress)

### Milestones

- [ ] Store Agent implementation
- [ ] Store location API integration
- [ ] Inventory checking by store
- [ ] Store availability API

### Key Deliverables

- Store information retrieval
- Per-store inventory checks

### Current Tasks

| Task | Status | Owner |
|------|--------|-------|
| Store Agent core logic | In Progress | Development Team |
| Store location endpoints | Pending | - |
| Availability checking | Pending | - |

---

## Phase 5: Production Hardening (Pending)

### Milestones

- [ ] Performance optimization
- [ ] Comprehensive testing
- [ ] Security audit
- [ ] Monitoring and alerting setup
- [ ] Documentation completion
- [ ] Deployment to production

### Key Deliverables

- Production-ready deployment
- Full observability
- Complete test coverage

---

## Success Metrics

| Metric | Target | Current | Status |
|--------|--------|---------|--------|
| Query Classification Accuracy | >90% | TBD | In Progress |
| First Response Time | <3s | TBD | In Progress |
| System Uptime | 99.5% | - | Pending |
| FAQ Resolution Rate | >85% | - | Pending |

---

## Technical Debt

| Item | Priority | Status |
|------|----------|--------|
| Store Agent completion | High | In Progress |
| Comprehensive unit tests | High | Pending |
| Integration tests | Medium | Pending |
| E2E test suite | Medium | Pending |
| API documentation (Swagger) | Low | Pending |

---

## Future Enhancements

| Feature | Priority | Description |
|---------|----------|-------------|
| Voice support | Low | Voice input/output |
| Image recognition | Low | Tire wear analysis |
| Predictive recommendations | Low | ML-based suggestions |
| Multi-channel support | Medium | LINE, KakaoTalk |
| Advanced analytics | Medium | Usage analytics |

---

## Dependencies

- Oracle database access
- AWS Bedrock access
- OpenAI API access
- Qdrant vector store
- Langfuse for tracing

---

## Notes

- Phase 1-3 completed with basic functionality
- Current focus: Phase 4 (Store Agent)
- Phase 5 will begin after Store Agent completion
