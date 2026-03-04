# T-Station AI Project Overview

## Project Summary

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea, designed to handle customer inquiries about tires through a multi-agent AI architecture. The system provides product recommendations, compatibility checks, FAQ support, and store information.

## Business Context

- **Client**: Hankook Tire Korea
- **Purpose**: AI-powered customer support for tire sales
- **Target Users**: HKT customers seeking tire information and purchases
- **Languages**: Korean, English, Vietnamese, Chinese, Japanese

## Technical Stack

### Core Technologies
- **API Framework**: FastAPI + Uvicorn
- **AI/LLM**: LangChain + LiteLLM with Bedrock Claude Haiku 4.5
- **Vector Store**: Qdrant (RAG for FAQ)
- **Task Queue**: Celery + Redis
- **Observability**: Langfuse for tracing

### Backend Services
- **Database**: Oracle (tstation-be)
- **Frontend**: Streamlit demo UI

### Infrastructure
- **Containerization**: Docker
- **Task Runner**: Just
- **Package Manager**: uv

---

## Product Development Requirements (PDR)

### Functional Requirements

#### FR-001: Multi-Agent Chat System
- **Description**: Implement a conversational AI system that routes customer queries to appropriate specialized agents
- **Priority**: Critical
- **Acceptance Criteria**:
  - User can send chat messages and receive responses
  - System correctly classifies queries into domains
  - Queries are routed to the appropriate sub-agent
  - Streaming responses are supported

#### FR-002: Domain Classification
- **Description**: Automatically classify incoming queries into predefined domains
- **Priority**: Critical
- **Acceptance Criteria**:
  - LEADING: General/unclear queries
  - DISCOVERY: Product research, recommendations, compatibility
  - SHOPPING: Price, stock, store inquiries
  - TRANSACTION: Purchase intent
  - SUPPORT: Warranty, returns, policies
  - Classification accuracy > 90% for clear-cut cases

#### FR-003: Product Discovery Agent
- **Description**: Provide tire recommendations, compatibility checks, and product descriptions
- **Priority**: High
- **Acceptance Criteria**:
  - Recommend tires based on vehicle type, driving conditions
  - Check compatibility between tires and vehicles
  - Provide detailed product descriptions

#### FR-004: FAQ Agent (RAG)
- **Description**: Answer policy questions using retrieval-augmented generation
- **Priority**: High
- **Acceptance Criteria**:
  - Use Qdrant vector store for FAQ retrieval
  - Integrate with OpenAI for response generation
  - Handle warranty, returns, and general policies

#### FR-005: Store Agent
- **Description**: Provide store information and availability
- **Priority**: Medium
- **Acceptance Criteria**:
  - Query store locations
  - Check tire availability at stores

#### FR-006: Multi-language Support
- **Description**: Support multiple languages for customer queries
- **Priority**: High
- **Acceptance Criteria**:
  - Detect language automatically
  - Support Korean, English, Vietnamese, Chinese, Japanese
  - Respond in the same language as the query

### Non-Functional Requirements

#### NFR-001: Performance
- **Description**: System must respond within acceptable time limits
- **Acceptance Criteria**:
  - First response within 3 seconds for simple queries
  - Streaming starts within 2 seconds

#### NFR-002: Scalability
- **Description**: System must handle concurrent users efficiently
- **Acceptance Criteria**:
  - Support 100+ concurrent users
  - Horizontal scaling via container orchestration

#### NFR-003: Reliability
- **Description**: System must be reliable and handle errors gracefully
- **Acceptance Criteria**:
  - 99.5% uptime
  - Graceful degradation when services fail
  - Proper error logging and alerting

#### NFR-004: Security
- **Description**: Protect sensitive data and API access
- **Acceptance Criteria**:
  - API key authentication required
  - No sensitive data in logs
  - Environment-based configuration

#### NFR-005: Observability
- **Description**: Provide visibility into system operations
- **Acceptance Criteria**:
  - Langfuse tracing for AI calls
  - Prometheus metrics endpoint
  - Health check endpoints

---

## Architecture Decisions

### AD-001: Multi-Agent Architecture
- **Decision**: Use specialized agents with a leading agent orchestrator
- **Rationale**: Different query types require different expertise; modular design allows independent improvement

### AD-002: Domain Routing
- **Decision**: Route queries based on domain classification
- **Rationale**: Ensures queries reach the most appropriate agent

### AD-002: RAG for FAQ
- **Decision**: Use Qdrant vector store for FAQ retrieval
- **Rationale**: Efficient similarity search for policy questions

### AD-003: Environment-Based Configuration
- **Decision**: Support LOCAL, DEV, STAGING, PROD environments
- **Rationale**: Separation of concerns between development stages

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Query Classification Accuracy | >90% | A/B testing |
| First Response Time | <3s | APM tracing |
| System Uptime | 99.5% | Monitoring |
| Customer Satisfaction | >4/5 | User feedback |
| FAQ Resolution Rate | >85% | Analytics |

---

## Timeline & Milestones

See [Project Roadmap](./project-roadmap.md) for detailed timeline.

---

## Risks & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM response quality | High | Prompt engineering, human feedback |
| Query classification errors | High | Fallback to leading agent |
| Qdrant availability | Medium | Cache frequently accessed FAQs |
| Oracle DB performance | High | Connection pooling, caching |
