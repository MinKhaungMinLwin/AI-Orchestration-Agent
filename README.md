# T-Station AI for Hankook Tire

T-Station AI is a conversational commerce chatbot for Hankook Tire Korea. It uses a multi-agent architecture with FastAPI to handle customer inquiries about tires, providing product recommendations, compatibility checks, and FAQ support.

## Architecture Overview

The system consists of three main components:

- **tstation-ai** (port 8000/9000): Main AI service with FastAPI, LangChain agents, RAG (Qdrant), and task queue (Celery/Redis)
- **tstation-be** (port 8001): Backend service connecting to Oracle database
- **tstation-ui-demo** (port 7777): Streamlit-based demo UI

## Deployment

### 1. Install Dependencies

Install **Just** (task runner):

```bash
curl -fsSL https://just.systems/install.sh | sudo bash -s -- --to /usr/local/bin
```

### 2. Environment Setup

Create or update the `.env` file with required keys (see `.env.example`).

### 3. Start Application

```bash
just start
```

### 4. API Access

- **Base URL**: `http://{YOUR_IP}:{NGINX_PORT}/api`
- **Authentication**: `Authorization: Bearer {API_SECRET_KEY}`

### 5. Test API

```bash
curl -X GET \
  "http://{YOUR_IP}:7777/api/test/success" \
  -H "accept: application/json" \
  -H "Authorization: Bearer {API_SECRET_KEY}"
```

## Development

### Prerequisites

- Python 3.12
- Just (task runner)
- uv (package manager)

### Running Services

```bash
# AI service (port 9000)
set -a && source .env && set +a && uv run app/tstation-ai/main.py

# BE service (port 8000)
set -a && source app/tstation-be/.env && set +a && uv run app/tstation-be/main.py

# UI demo (port 7777)
uv run streamlit run app/tstation-ui-demo/Home.py --server.port 7777 --server.address 0.0.0.0
```

### Code Quality

```bash
just lint    # Check code with ruff
just fmt     # Format code with ruff + isort
```
