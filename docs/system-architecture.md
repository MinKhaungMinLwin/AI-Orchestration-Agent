# T-Station AI System Architecture

## Overview

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea. It uses a multi-agent architecture with FastAPI to handle customer inquiries about tires, providing product recommendations, compatibility checks, FAQ support, and store information.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Client Applications                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Web UI     │  │  Mobile App │  │  Line API   │  │  Other Integrations │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
└─────────┼───────────────┼────────────────┼────────────────────┼────────────┘
          │               │                │                    │
          └───────────────┴────────────────┴────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Nginx Reverse Proxy                                │
│                              (Port 9000)                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         T-Station AI Service                                │
│                         (FastAPI, Port 8000)                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                         API Layer                                       │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  │ │
│  │  │  /chat       │  │  /example    │  │  /health, /metrics          │  │ │
│  │  │  (POST)      │  │  _questions  │  │  (Monitoring)              │  │ │
│  │  │              │  │  (GET)       │  │                             │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                     Service Layer                                        │ │
│  │  ┌──────────────────────────┐  ┌───────────────────────────────────┐   │ │
│  │  │  TStationChatService    │  │  ExampleQuestionsService          │   │ │
│  │  │  - chat()               │  │  - get_example_questions()        │   │ │
│  │  └───────────┬──────────────┘  └───────────────────────────────────┘   │ │
│  └──────────────┼───────────────────────────────────────────────────────────┘ │
│                 │                                                             │
│                 ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                      Agent Layer (Multi-Agent)                          │ │
│  │                                                                          │ │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                    Domain Router                                   │ │ │
│  │  │                 (router.py)                                        │ │ │
│  │  └────────────────────────────────────────────────────────────────────┘ │ │
│  │                                    │                                      │ │
│  │        ┌───────────────────────────┼───────────────────────────┐        │ │
│  │        │                           │                           │        │ │
│  │        ▼                           ▼                           ▼        │ │
│  │  ┌──────────────┐         ┌──────────────┐         ┌──────────────┐   │ │
│  │  │   Leading    │         │  Discovery   │         │     FAQ      │   │ │
│  │  │   Agent      │────────▶│   Agent      │         │    Agent     │   │ │
│  │  │ (Orchestrator│         │ (Recommend)  │         │    (RAG)     │   │ │
│  │  └──────────────┘         └──────────────┘         └──────────────┘   │ │
│  │        │                                                           │        │ │
│  │        │                           ┌──────────────┐                │        │ │
│  │        │                           │    Store     │                │        │ │
│  │        └──────────────────────────▶│    Agent     │                │        │ │
│  │                                    │ (In Progress)│                │        │ │
│  │                                    └──────────────┘                │        │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                 │                                                             │
│                 ▼                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    External Services                                     │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────┐  │ │
│  │  │ LiteLLM/     │  │   Qdrant      │  │   Langfuse   │  │  Redis  │  │ │
│  │  │ Bedrock      │  │ (Vector Store)│  │  (Tracing)   │  │  Queue  │  │ │
│  │  │ (LLM)        │  │               │  │              │  │         │  │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └─────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        T-Station Backend (BE)                                │
│                        (FastAPI, Port 8001)                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    API Routers                                           │ │
│  │  ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌────────────┐ ┌───────────┐  │ │
│  │  │  Shop    │ │  Price  │ │Inventory │ │Recommendation│ │  Order   │  │ │
│  │  └──────────┘ └─────────┘ └──────────┘ └────────────┘ └───────────┘  │ │
│  │  ┌──────────┐ ┌─────────┐ ┌──────────┐ ┌────────────┐ ┌───────────┐  │ │
│  │  │  Quick   │ │Compati- │ │Description│ │    FAQ    │ │Escalation │  │ │
│  │  │  Order   │ │  bility │ │           │ │            │ │          │  │ │
│  │  └──────────┘ └─────────┘ └──────────┘ └────────────┘ └───────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────────┐ │
│  │                    Database                                               │ │
│  │  ┌────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                    Oracle Database                                   │ │ │
│  │  │  - Product catalog                                                 │ │ │
│  │  │  - Pricing                                                         │ │ │
│  │  │  - Inventory                                                        │ │ │
│  │  │  - Customer data                                                   │ │ │
│  │  └────────────────────────────────────────────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. API Layer (`tstation-ai/api/`)

| Component | Description |
|-----------|-------------|
| `router.py` | Main router with environment-based configuration |
| `monitoring.py` | Health checks, test endpoints, Prometheus metrics |
| `tstation/chat.py` | Main chat endpoint (`POST /chat`) |
| `tstation/example_question.py` | Example questions endpoint |

### 2. Service Layer (`tstation-ai/services/`)

| Service | Description |
|---------|-------------|
| `TStationChatService` | Main chat processing service |
| `ExampleQuestionsService` | Returns example questions per language |

### 3. Agent Layer (`tstation-ai/services/tstation/agents/`)

#### Domain Router

Routes incoming queries to appropriate agents based on domain classification:

| Domain | Agent | Description |
|--------|-------|-------------|
| LEADING | Leading Agent | General/unclear queries |
| DISCOVERY | Discovery Agent | Product research, recommendations |
| SHOPPING | Discovery Agent | Price, stock, store |
| TRANSACTION | Leading Agent | Purchase intent |
| SUPPORT | FAQ Agent | Warranty, returns, policies |

#### Leading Agent (`a_leading_agent/`)

- Central orchestrator for all chat requests
- Classifies user queries into domains
- Routes to appropriate sub-agent
- Handles fallback for unclear queries

#### Discovery Agent (`b_discovery_agent/`)

Provides tire recommendations and information:

- **Product Recommendations**: Suggests tires based on vehicle, driving conditions
- **Compatibility Checks**: Verifies tire-vehicle compatibility
- **Product Descriptions**: Detailed tire specifications

Tools available:
- Price lookup
- Inventory check
- Description generation

#### FAQ Agent (`faq_agent/`)

Retrieval-Augmented Generation (RAG) for policy questions:

- **Vector Store**: Qdrant for semantic search
- **LLM Integration**: OpenAI for response generation
- **Data Sources**: Warranty policies, return policies, FAQs

Scripts:
- `load_faqs_to_qdrant.py`: Load FAQs to vector store
- `load_sample_reviews.py`: Load sample data
- `test_retrieval_logic.py`: Test retrieval

#### Store Agent (`store_agent/`)

- Store information and availability (in development)

### 4. Backend Layer (`tstation-be/`)

RESTful API for Hankook Tire data:

| Router | Description |
|--------|-------------|
| `shop.py` | Shop/store information |
| `price.py` | Tire pricing data |
| `inventory.py` | Stock availability |
| `recommendation.py` | Product recommendations |
| `order.py` | Order management |
| `quick_order.py` | Quick ordering |
| `compatibility.py` | Tire-vehicle compatibility |
| `description.py` | Product descriptions |
| `faq.py` | FAQ data |
| `escalation.py` | Human escalation |

### 5. Data Flow

```
User Query
    │
    ▼
┌─────────────────┐
│  Chat Endpoint  │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│ TStationChatService │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Leading Agent     │
│ (Domain Classifier) │
└────────┬────────────┘
         │
    ┌────┴────┬──────────┐
    │         │          │
    ▼         ▼          ▼
┌───────┐ ┌────────┐ ┌──────┐
│Discovery│ │  FAQ  │ │Store │
│ Agent  │ │ Agent │ │Agent │
└───┬───┘ └───┬────┘ └───┬──┘
    │         │          │
    └────┬────┴──────────┘
         │
         ▼
┌─────────────────────┐
│  T-Station Backend  │
│  (Oracle DB)        │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│   Response to User  │
└─────────────────────┘
```

## Environment Configuration

| Environment | Description | Port |
|-------------|-------------|------|
| LOCAL | Local development | 8000/8001/7777 |
| DEV | Development server | 9000 |
| STAGING | Staging environment | 9000 |
| PROD | Production | 9000 |

## External Integrations

| Service | Purpose | Provider |
|---------|---------|----------|
| Bedrock Claude Haiku 4.5 | LLM for AI responses | AWS |
| OpenAI | LLM for FAQ generation | OpenAI |
| Qdrant | Vector store for RAG | Qdrant |
| Langfuse | Tracing and observability | Langfuse |
| Redis | Queue system | Redis |
| Oracle | Product/customer data | Oracle |

## Monitoring & Observability

- **Health Checks**: `/health` endpoint
- **Metrics**: Prometheus format at `/metrics`
- **Tracing**: Langfuse integration
- **Logging**: Structured logging with log levels

## Security

- API key authentication via `API_SECRET_KEY`
- Environment-based configuration
- No sensitive data in logs
